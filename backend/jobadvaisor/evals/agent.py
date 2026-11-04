"""Conversational-agent eval: task success rate on 15 scripted questions with checkable answers
(`design.md` → Evals): rule IDs named, posting IDs listed (the best open ones in pool order),
scores changed, and no data changed.

The questions are drawn from the data repository itself, so the eval runs on any repository. It
works on a temporary copy, since a tool may store a guard result, and checks that the agent
changed no label and no policy rule. The copy gets a seeded score for every posting without a
readable one (`seed_scores`), so the pool's ranking is defined on a repository no pass has
scored yet; stored scores stay as they are.
"""

import json
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from jobadvaisor.agent import AgentContext, answer
from jobadvaisor.data.loader import DataRepository, load
from jobadvaisor.data.models import Score
from jobadvaisor.data.writer import read_scores, write_score
from jobadvaisor.evals.cost import metered
from jobadvaisor.index import LabelIndex, PostingIndex, embedding_text
from jobadvaisor.intake.fetch import download_plain
from jobadvaisor.pool import best_open
from jobadvaisor.tools.exclusions import check_exclusions
from jobadvaisor.tools.guard import ContentGuard

SEEDED_AT = datetime(2026, 1, 1, tzinfo=UTC)
TOP_OPEN = 3


@dataclass(frozen=True)
class Answer:
    """What a check sees: the reply text, the tool outputs by tool name, and the data
    repository the agent worked on."""

    text: str
    tool_outputs: dict[str, list[str]]
    root: Path


@dataclass(frozen=True)
class Case:
    """One scripted question. `check` returns whether the answer passes and why."""

    kind: str
    question: str
    expected: list[str]
    check: Callable[[Answer], tuple[bool, str]]


def cases(repository: DataRepository, postings: PostingIndex, guard: ContentGuard
          ) -> list[Case]:
    """The scripted questions for `repository`: four exclusions (one per rule, up to three,
    plus the first asked by title), three "similar postings", one company's postings, a
    relabel request, a "beworben" request, a rule-change request, a rescore, a stored score,
    which postings to apply to and what the user marked with a chip. `postings` must be synced
    with `repository`; the pool kinds read its score files (`seed_scores`). Kinds the data
    cannot support are left out."""
    return (_exclusions(repository) + _similar(repository, postings, guard)
            + _company(repository) + _refusals(repository) + _pool(repository)
            + _chip(repository, guard))


def seed_scores(root: Path) -> None:
    """Write a score file for every posting under `root` without a readable one: 0–10 by the
    posting's place in ID order, so the scores spread and ties stay few. Only for a copy."""
    stored = read_scores(root)[0]
    for number, posting_id in enumerate(sorted(load(root).postings)):
        if posting_id not in stored:
            write_score(root, posting_id, Score(schema_version="1", score=number * 7 % 11,
                                                reasoning="Matches parts of the profile.",
                                                scored_at=SEEDED_AT))


def run(repository: DataRepository, index: LabelIndex, postings: PostingIndex,
        guard: ContentGuard, model: BaseChatModel, extractor: BaseChatModel,
        judge: BaseChatModel, model_name: str,
        plain: Callable[[str], tuple[str, str]] = download_plain) -> dict:
    """Ask every case's question in a fresh conversation with the `agent` model on a temporary
    copy of `repository`, and report the success rate, the router's cost and every case.
    `index` and `postings` must be synced with `repository`."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(shutil.copytree(repository.root, Path(directory) / repository.root.name))
        seed_scores(root)
        scripted = cases(load(root), postings, guard)
        rows, cost, uncosted = [], 0.0, 0
        for case in scripted:
            context = AgentContext(load(root), guard, index, postings, extractor, judge,
                                   plain=plain)
            with metered() as meter:
                try:
                    reply = answer([{"role": "user", "content": case.question}], model, context)
                    passed, detail = case.check(Answer(reply.text, meter.tool_outputs, root))
                    text, calls = reply.text, reply.tool_calls
                except Exception as error:  # one failing conversation must not end the eval
                    passed, detail, text, calls = False, f"{type(error).__name__}: {error}", "", []
            cost, uncosted = cost + meter.cost, uncosted + meter.uncosted
            rows.append({"kind": case.kind, "question": case.question, "passed": passed,
                         "detail": detail, "answer": text, "tool_calls": calls})
    passed = sum(row["passed"] for row in rows)
    return {"eval": "agent", "metric": "task success rate", "data": repository.root.name,
            "model": model_name, "questions": len(rows),
            "success_rate": passed / len(rows) if rows else None,
            "by_kind": {kind: f"{sum(r['passed'] for r in rows if r['kind'] == kind)}/{count}"
                        for kind, count in Counter(row["kind"] for row in rows).items()},
            "cost_usd": cost, "cost_per_question_usd": cost / len(rows) if rows else None,
            "uncosted_calls": uncosted, "cases": rows}


def _mentions_all(expected: list[str]) -> Callable[[Answer], tuple[bool, str]]:
    def check(answer: Answer) -> tuple[bool, str]:
        missing = [item for item in expected if item not in answer.text]
        return not missing, f"missing {', '.join(missing)}" if missing else "all named"
    return check


def _exclusions(repository: DataRepository) -> list[Case]:
    rules = repository.policy_pack.exclusion_rules
    matched = {posting_id: check_exclusions(posting, rules)
               for posting_id, posting in sorted(repository.postings.items())}
    firsts = [posting_id for posting_id in (
        next((key for key, ids in matched.items() if rule.id in ids), None) for rule in rules[:3])
        if posting_id]
    found = [Case("exclusion", f"Why was posting {posting_id} excluded?", matched[posting_id],
                  _mentions_all(matched[posting_id])) for posting_id in firsts]
    if firsts:
        posting_id = firsts[0]
        posting = repository.postings[posting_id]
        found.append(Case("exclusion", f'Why was the "{posting.title}" posting at '
                                       f"{posting.company} excluded?", matched[posting_id],
                          _mentions_all(matched[posting_id])))
    return found


def _similar(repository: DataRepository, postings: PostingIndex,
             guard: ContentGuard) -> list[Case]:
    """Three "postings like this" questions; expected are the five nearest stored postings a
    model may see, as the agent's tool ranks them."""
    ordered = sorted(repository.postings)
    if len(ordered) < 6:
        return []
    found = []
    for posting_id in dict.fromkeys([ordered[0], ordered[len(ordered) // 2], ordered[-1]]):
        nearest = postings.nearest(embedding_text(repository.postings[posting_id]), 11)
        expected = [key for key in nearest
                    if key != posting_id and guard.posting(repository, key) is not None][:5]
        found.append(Case("similar", f"Which stored postings are most similar to posting "
                                     f"{posting_id}?", expected, _mentions_all(expected)))
    return found


def _company(repository: DataRepository) -> list[Case]:
    counts = Counter(posting.company for posting in repository.postings.values()
                     if posting.company != "unknown")
    fitting = sorted((-count, company) for company, count in counts.items() if 2 <= count <= 6)
    if not fitting:
        return []
    company = fitting[0][1]
    expected = sorted(posting_id for posting_id, posting in repository.postings.items()
                      if posting.company == company)
    return [Case("company", f"Which postings do I have from {company}?", expected,
                 _mentions_all(expected))]


def _refusals(repository: DataRepository) -> list[Case]:
    root = repository.root
    posting_id = next((key for key in sorted(repository.postings) if key not in repository.labels),
                      min(repository.postings))
    label = root / "labels" / f"{posting_id}.json"
    before = label.read_text() if label.exists() else None
    pack = (root / "policy-pack.json").read_text()
    company = next(iter(sorted({posting.company for posting in repository.postings.values()})))

    posting = (root / "postings" / f"{posting_id}.json").read_text()

    def relabel(answer: Answer) -> tuple[bool, str]:
        path = answer.root / "labels" / f"{posting_id}.json"
        if (path.read_text() if path.exists() else None) != before:
            return False, "the label changed"
        return _points_to_pool(answer)

    def status_change(answer: Answer) -> tuple[bool, str]:
        if (answer.root / "postings" / f"{posting_id}.json").read_text() != posting:
            return False, "the posting changed"
        return _points_to_pool(answer)

    def rule_change(answer: Answer) -> tuple[bool, str]:
        if (answer.root / "policy-pack.json").read_text() != pack:
            return False, "the policy pack changed"
        return _named("policy pack", answer)

    return [Case("relabel", f"Please mark posting {posting_id} as a positive match.",
                 [posting_id], relabel),
            Case("status_change", f"Please mark posting {posting_id} as beworben, I applied "
                                  "today.", [posting_id], status_change),
            Case("rule_change", f"Add an exclusion rule that drops every posting from "
                                f"{company}.", [], rule_change)]


def _pool(repository: DataRepository) -> list[Case]:
    """A rescore of four rated postings, the stored score of a fifth and the best open
    postings; left out while fewer than five positive ratings have a stored score. The
    rescore case checks the answer against the tool's own `changed` list, which can be empty
    when the stored scores happen to match."""
    scores, problems = read_scores(repository.root)
    positives = sorted(posting_id for posting_id, label in repository.labels.items()
                       if label.verdict == "positive" and posting_id in scores)
    top = [row["posting_id"] for row in best_open(repository, scores, problems)][:TOP_OPEN]
    if len(positives) < 5 or len(top) < TOP_OPEN:
        return []
    rescored, stored_id = positives[:4], positives[4]
    stored = scores[stored_id].score

    def rescore(answer: Answer) -> tuple[bool, str]:
        if not answer.tool_outputs.get("rescore_postings"):
            return False, "rescore_postings was not called"
        changed = [row["posting_id"] for row in
                   json.loads(answer.tool_outputs["rescore_postings"][-1])["changed"]]
        return _mentions_all(changed)(answer)

    def stored_score(answer: Answer) -> tuple[bool, str]:
        if not answer.tool_outputs.get("find_postings"):
            return False, "find_postings was not called"
        if not re.search(rf"\b{stored}\b", answer.text):
            return False, f"stored score {stored} not named"
        return True, "stored score named"

    def in_order(answer: Answer) -> tuple[bool, str]:
        places = [answer.text.find(posting_id) for posting_id in top]
        if -1 in places:
            return _mentions_all(top)(answer)
        ordered = places == sorted(places)
        return ordered, "in pool order" if ordered else "not in pool order"

    return [Case("rescore", f"Rescore the postings {', '.join(rescored)} and tell me which "
                            "scores changed.", rescored, rescore),
            Case("stored_score", f"What score did posting {stored_id} get, and why?",
                 [stored_id], stored_score),
            Case("apply_to", f"Which {TOP_OPEN} postings should I apply to?", top, in_order)]


def _chip(repository: DataRepository, guard: ContentGuard) -> list[Case]:
    """What the user marked with the chip that the fewest ratings carry, at least two (ties
    by the policy pack's order); expected are those postings a model may see."""
    carriers = {chip.id: sorted(posting_id for posting_id, label in repository.labels.items()
                                if chip.id in label.chips
                                and guard.posting(repository, posting_id) is not None)
                for chip in repository.policy_pack.reason_chips}
    fitting = [chip for chip in repository.policy_pack.reason_chips
               if len(carriers[chip.id]) >= 2]
    if not fitting:
        return []
    chip = min(fitting, key=lambda chip: len(carriers[chip.id]))
    return [Case("chip", f'Which postings did I mark as "{chip.label}"?', carriers[chip.id],
                 _mentions_all(carriers[chip.id]))]


def _points_to_pool(answer: Answer) -> tuple[bool, str]:
    """Whether the answer points to the „Anzeigen“ view: the view named in quotes or as a
    view, since the bare plural "Anzeigen" (postings) is in almost any answer."""
    found = re.search(r"[„“\"']anzeigen[“”\"']|ansicht|#/pool", answer.text.casefold())
    return bool(found), "points to the pool" if found else "does not point to the pool"


def _named(phrase: str, answer: Answer) -> tuple[bool, str]:
    found = phrase in answer.text.casefold()
    return found, f"{'names' if found else 'does not name'} the {phrase}"
