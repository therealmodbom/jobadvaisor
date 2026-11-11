"""The conversational agent (`design.md` → API and frontend; spec `job-agent`): a ReAct agent
(role `agent`) over the shared tools, plus read-only lookups of stored postings and the pool.

No tool writes user data: there is no label-, rule- or profile-writing tool, so "no silent data
changes" holds in code. Every text a tool returns from a posting, a page or a search passes the
content guard first; the one write any tool performs is the guard result of an unscreened
posting, which the model neither triggers by choice nor shapes.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, wrap_tool_call
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from jobadvaisor import pool
from jobadvaisor.data.loader import DataRepository
from jobadvaisor.data.models import Score
from jobadvaisor.data.writer import read_scores
from jobadvaisor.index import LabelIndex, PostingIndex, embedding_text
from jobadvaisor.intake.fetch import download_plain
from jobadvaisor.intake.ladder import LadderResult, fetch_posting, login_wall_hosts
from jobadvaisor.tools import exclusions, extraction, research, scoring, similar
from jobadvaisor.tools.guard import WITHHELD, ContentGuard
from jobadvaisor.tools.prompts import DATA_RULE, data_block

MAX_MODEL_CALLS = 12
MAX_PAGE_CHARACTERS = 4000
MAX_LISTED = 20
AGENT_TOOLS = ["find_postings", "best_open_postings", "check_exclusions", "extract_features",
               "find_similar_postings", "score_posting", "rescore_postings", "research_company",
               "fetch_posting"]
INSTRUCTIONS = (
    "You help the user find the job postings worth applying to and understand their scores, "
    "exclusions and ratings. Act only through your tools, and never invent posting IDs, rule "
    "IDs or scores: take them from a tool result and cite them. Name a posting by its title "
    "and company with its ID in parentheses, never by its ID alone, and make that name a "
    "Markdown link to the posting's page, e.g. [Backend Engineer, Acme (acme-1)](#/anzeigen/"
    "acme-1). For which postings to apply to or which fit best, call best_open_postings and "
    "list its postings in its order with score, the user's rating and status. For how the user "
    "rated a posting, give find_postings' your_rating; find_postings also searches the reason "
    "chips and notes of the ratings, so use it for what the user marked with a chip, and list "
    "only postings whose rating carries it. A score is the judge's estimate, never the user's "
    "rating. To explain an exclusion, name the rule IDs check_exclusions returns. To explain a "
    "score, cite the reasoning of find_postings' stored_score or the rated examples. For "
    "postings like a given one, list the IDs find_similar_postings returns, in its order. To "
    "rescore, call rescore_postings with the postings in question and list those whose score "
    "changed, with the old and new score; rescoring stores nothing, and do not promise that "
    "a pass will store the new scores. You cannot create, change or delete labels, exclusion "
    "rules, the profile or a posting's application status: when asked to rate or relabel, say that "
    "ratings are given in the „Anzeigen“ view; when asked to mark a posting „beworben“ or "
    "„erledigt“, say that the status is set in the „Anzeigen“ view; rules live in the Policy "
    "Pack. Change nothing then. Always answer in German, whatever language the user or a "
    "posting uses, and keep posting IDs, rule IDs and scores as the tools return them. "
    + " ".join(DATA_RULE.format(tag=tag) for tag in ("posting", "page", "results"))
)


@dataclass(frozen=True)
class AgentContext:
    """What the tools work with, built fresh for each message so they see the data repository
    as it is now. `index` holds the rated postings (scoring examples), `postings` every stored
    posting (similar postings). `fetch` runs the fetch ladder (default: the real one with the
    policy pack's login-walled hosts); `plain` fetches the company website for
    `research_company`; `search` is a web search, `None` while no provider is configured."""

    repository: DataRepository
    guard: ContentGuard
    index: LabelIndex
    postings: PostingIndex
    extractor: BaseChatModel
    judge: BaseChatModel
    fetch: Callable[[str], LadderResult] | None = None
    plain: Callable[[str], tuple[str, str]] = download_plain
    search: Callable[[str], str] | None = None


@dataclass(frozen=True)
class Reply:
    """The agent's answer text and the tool calls it made, as `{"name", "args"}`."""

    text: str
    tool_calls: list[dict] = field(default_factory=list)


def answer(messages: list[dict], model: BaseChatModel, context: AgentContext) -> Reply:
    """Answer the conversation `messages` (`{"role": "user" | "assistant", "content"}`, the
    last one the user's) with the `agent` chat model, in at most `MAX_MODEL_CALLS` model
    calls."""
    agent = create_agent(model, agent_tools(context), system_prompt=INSTRUCTIONS,
                         middleware=[ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS,
                                                              exit_behavior="end"),
                                     tool_errors])
    history = [HumanMessage(m["content"]) if m["role"] == "user" else AIMessage(m["content"])
               for m in messages]
    produced = agent.invoke({"messages": history})["messages"][len(history):]
    replies = [message for message in produced if isinstance(message, AIMessage)]
    calls = [{"name": call["name"], "args": call["args"]}
             for message in replies for call in message.tool_calls]
    return Reply(replies[-1].text if replies else "", calls)


@wrap_tool_call
def tool_errors(request, handler):
    """Agent middleware: a failing tool answers "tool failed: <error type>" instead of ending
    the conversation. Only the type is shown, since an error message can quote model output
    derived from third-party text."""
    try:
        return handler(request)
    except Exception as error:
        return ToolMessage(f"tool failed: {type(error).__name__}",
                           tool_call_id=request.tool_call["id"], name=request.tool_call["name"])


def agent_tools(context: AgentContext) -> list:
    """The agent's tools over `context`, named as in `AGENT_TOOLS`."""
    repository, guard = context.repository, context.guard
    synced, synced_postings, read = [], [], []
    chips = {chip.id: chip.label for chip in repository.policy_pack.reason_chips}

    def scores() -> tuple[dict[str, Score], dict[str, str]]:
        """The pool's score files and their problems (`read_scores`), read once per message."""
        if not read:
            read.append(read_scores(repository.root))
        return read[0]

    def index() -> LabelIndex:
        """The label index, synced once per message (slice-4 ruling: sync before querying)."""
        if not synced:
            context.index.sync(repository)
            synced.append(True)
        return context.index

    def shown(posting_id: str):
        """The stored posting if a model may see it, else `None`; fails closed."""
        try:
            return guard.posting(repository, posting_id)
        except Exception:
            return None

    def rated_texts(posting_id: str) -> list[str]:
        """The chip labels and the note of the posting's label, for the text search."""
        label = repository.labels.get(posting_id)
        return [chips.get(chip, chip) for chip in label.chips] + [label.note or ""] if label else []

    def rescored(posting_id: str) -> int | str:
        if (posting := shown(posting_id)) is None:
            return WITHHELD
        examples = similar.find_similar_labeled(guard, index(), repository, posting,
                                                posting_id=posting_id)
        return scoring.score_posting(posting, repository.profile, repository.policy_pack,
                                     examples, context.judge).score

    @tool
    def find_postings(query: str) -> str:
        """Find stored postings whose ID, title, company or the user's rating (a reason chip or
        the note) contains `query`; lists their IDs with the user's own rating (verdict, reason
        chips, note; null while unrated) and the stored pool score with the judge's reasoning
        (null while the posting has no score)."""
        wanted = query.casefold()
        found = sorted(posting_id for posting_id, posting in repository.postings.items()
                       if any(wanted in value.casefold()
                              for value in (posting_id, posting.title, posting.company,
                                            *rated_texts(posting_id))))
        stored = scores()[0]
        rows = []
        for posting_id in found[:MAX_LISTED]:
            posting = shown(posting_id)
            label = repository.labels.get(posting_id)
            rating = label and {"kind": label.kind, "verdict": label.verdict, "note": label.note,
                                "chips": [chips.get(chip, chip) for chip in label.chips]
                                } | _strength(label.strength)
            score = stored.get(posting_id)
            # the reasoning derives from the posting's text, so it is shown only with it
            kept = score and {"score": score.score} | (
                {"reasoning": score.reasoning} if posting else {})
            rows.append({"posting_id": posting_id, "your_rating": rating, "stored_score": kept}
                        | ({"title": posting.title, "company": posting.company} if posting
                           else {"content": WITHHELD}))
        return data_block("results", _json({"total": len(found), "postings": rows}))

    @tool
    def best_open_postings(limit: int = 5, statuses: list[str] | None = None) -> str:
        """The best-fitting postings of the whole pool, in the pool's ranking (rated positive
        first, then unrated by stored score), each with score, the user's rating, application
        status and its page address; postings rated negative, excluded or held and the pool's
        exploration picks are left out. Only open postings unless `statuses` names others
        ("open", "applied" = beworben, "done" = erledigt). At most 20."""
        ranked = pool.best_open(repository, *scores(), tuple(statuses or ["open"]))
        rows = []
        for row in ranked[:max(1, min(limit, MAX_LISTED))]:
            posting_id, label = row["posting_id"], row["label"]
            posting = shown(posting_id)
            rows.append({"posting_id": posting_id, "score": row["score"], "status": row["status"],
                         "your_rating": label and label["verdict"] and {
                             "verdict": label["verdict"],
                             "chips": [chips.get(chip, chip) for chip in label["chips"]]
                         } | _strength(label["strength"]),
                         "page": f"#/anzeigen/{posting_id}"}
                        | ({"title": posting.title, "company": posting.company} if posting
                           else {"content": WITHHELD}))
        return _json(rows)

    @tool
    def check_exclusions(posting_id: str) -> str:
        """The exclusion rules a stored posting matches, as in a triage run, and its content
        guard state."""
        if posting_id not in repository.postings:
            return f"no posting {posting_id}"
        rules = repository.policy_pack.exclusion_rules
        matched = exclusions.check_exclusions(repository.postings[posting_id], rules)
        stored = repository.postings[posting_id].guard
        state = ("unscreened" if stored is None else "released" if stored.released_at
                 else "flagged" if stored.flagged else "clean")
        return _json({"posting_id": posting_id, "excluded": bool(matched) or state == "flagged",
                      "rules": matched, "content_guard": state,
                      "rule_details": [rule.model_dump(exclude={"schema_version"})
                                       for rule in rules if rule.id in matched]})

    @tool
    def extract_features(posting_id: str) -> str:
        """Extract the policy pack's features from a stored posting."""
        if posting_id not in repository.postings:
            return f"no posting {posting_id}"
        if (posting := shown(posting_id)) is None:
            return WITHHELD
        features = extraction.feature_set(repository.policy_pack.feature_set)
        return _json(extraction.extract_features(posting, features, context.extractor,
                                                 repository.company_of(posting)))

    @tool
    def find_similar_postings(posting_id: str, k: int = 5) -> str:
        """The stored postings most similar to a stored posting, rated or not, most similar
        first, with the user's verdict (and its strength, when set) where there is one (k at
        most 20)."""
        if posting_id not in repository.postings:
            return f"no posting {posting_id}"
        k = max(1, min(k, MAX_LISTED))
        if not synced_postings:
            context.postings.sync(repository)
            synced_postings.append(True)
        # ponytail: 2k+1 candidates, so more than k+1 withheld neighbours shrink the result
        nearest = context.postings.nearest(embedding_text(repository.postings[posting_id]),
                                           2 * k + 1)
        rows = []
        for found in nearest:
            if found != posting_id and (posting := shown(found)) is not None:
                label = repository.labels.get(found)
                rows.append({"posting_id": found, "title": posting.title,
                             "company": posting.company,
                             "verdict": label.verdict if label else None}
                            | _strength(label.strength if label else None))
        return _json(rows[:k])

    @tool
    def score_posting(posting_id: str) -> str:
        """Score a stored posting now (0–10) with the labels stored at this moment."""
        if posting_id not in repository.postings:
            return f"no posting {posting_id}"
        if (posting := shown(posting_id)) is None:
            return WITHHELD
        examples = similar.find_similar_labeled(guard, index(), repository, posting,
                                                posting_id=posting_id)
        scored = scoring.score_posting(posting, repository.profile, repository.policy_pack,
                                       examples, context.judge)
        return _json(vars(scored))

    @tool
    def rescore_postings(posting_ids: list[str]) -> str:
        """Score the named stored postings (at most 20) again with the labels stored now and
        compare with their stored pool score (`before` null without one); lists the postings
        whose score changed, those unchanged and those that failed. Stores nothing: the pool's
        scores change only through a pass or a single score the user starts."""
        stored = scores()[0]
        # ponytail: one judge call per posting, sequential; batch if the lists grow large
        changed, unchanged, failed = [], [], []
        for posting_id in list(dict.fromkeys(posting_ids))[:MAX_LISTED]:
            if posting_id not in repository.postings:
                failed.append({"posting_id": posting_id, "error": "no such posting"})
                continue
            try:
                after = rescored(posting_id)
            except Exception as error:  # one bad answer must not end the rescoring
                # the type only, as in tool_errors: a message can quote third-party text
                failed.append({"posting_id": posting_id, "error": type(error).__name__})
                continue
            before = stored[posting_id].score if posting_id in stored else None
            if after == WITHHELD:
                failed.append({"posting_id": posting_id, "error": WITHHELD})
            elif after != before:
                changed.append({"posting_id": posting_id, "before": before, "after": after})
            else:
                unchanged.append(posting_id)
        return _json({"changed": changed, "unchanged": unchanged, "failed": failed})

    @tool(name_or_callable="research_company")
    def research_company_tool(company: str, website: str | None = None) -> str:
        """What the user's stored postings and the employer's website say about a company."""
        return research.research_company(company, repository, guard, website=website,
                                         plain=context.plain, search=context.search)

    @tool(name_or_callable="fetch_posting")
    def fetch_posting_tool(url: str) -> str:
        """Fetch a job posting from a URL (not stored); returns its text."""
        walled = login_wall_hosts(repository.policy_pack)
        found = (context.fetch or (lambda target: fetch_posting(target, walled)))(url)
        if found.page is None:
            return "no posting text found: " + "; ".join(
                f"{attempt.step}: {attempt.outcome}" for attempt in found.attempts)
        text = f"URL: {found.page.url}\n\n{found.page.text[:MAX_PAGE_CHARACTERS]}"
        try:
            screened = guard.third_party(text)
        except Exception:  # a failed screening withholds, never passes text unscreened
            screened = WITHHELD
        return screened if screened == WITHHELD else data_block("page", screened)

    return [find_postings, best_open_postings, check_exclusions, extract_features,
            find_similar_postings, score_posting, rescore_postings, research_company_tool,
            fetch_posting_tool]


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _strength(strength: str | None) -> dict:
    """`{"strength": ...}` for a rating that has one, else `{}`, so a plain yes or no reads as
    before."""
    return {"strength": strength} if strength else {}
