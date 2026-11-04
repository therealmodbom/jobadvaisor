"""Generate the fictional demo persona data repository in `fixtures/demo-persona/`.

Run `uv run python -m jobadvaisor.data.demo_persona` in `backend/` and commit the output.
The seed is fixed, so a run reproduces the committed fixture exactly, which
`tests/test_demo_persona.py` checks. A run replaces `postings/`, `labels/` and `companies/`
(one record per employer, its facts following the stage the postings state), so hand-written
fixtures (expected features, injected postings) belong in a directory of their own.

Everything is invented: a mid-level mobile developer, fictional towns, companies named
"Demo Co. <tree>", URLs on the reserved example.com and example.org domains. A hidden preference
function decides each verdict, so ratings are consistent enough for evals to learn from. Exactly
one rating mixes chips of both polarities (see `_mix_one_rating`).
"""

import random
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from jobadvaisor.data.models import (
    Company,
    Guard,
    Label,
    PolicyPack,
    Posting,
    Profile,
    company_id,
    slug,
)
from jobadvaisor.data.writer import write_company, write_label
from jobadvaisor.settings import REPOSITORY_ROOT

FIXTURE_DIRECTORY = REPOSITORY_ROOT / "fixtures" / "demo-persona"
SEED = 7
START = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
POSTING_COUNT = 150
IMPORTED = 30
THRESHOLD = 2.5
STRONG_MARGIN = 1.0  # utility distance from THRESHOLD from which a rating is strong

# Each attribute value maps to its weight in the hidden preference function.
ROLES = {  # title, role type, stack choices
    "Android Developer": ("android", ["kotlin", "java"], 2),
    "Mobile Developer (Kotlin Multiplatform)": ("cross-platform", ["kotlin", "swift"], 2),
    "iOS Developer": ("ios", ["swift"], 0),
    "Flutter Developer": ("cross-platform", ["dart"], 1),
    "React Native Developer": ("cross-platform", ["typescript"], 0),
    "Mobile QA Engineer": ("qa", ["kotlin", "python"], -1),
    "Backend Developer (Mobile APIs)": ("backend", ["kotlin", "go", "python"], 0),
    "Game Client Developer": ("game", ["csharp"], -2),
}
SENIORITY = {"junior": -2, "mid": 1, "senior": 1, "lead": -1}
DOMAINS = {"fitness": 2, "education": 2, "health": 1, "travel": 0, "logistics": 0, "media": 0,
           "banking": -1, "gaming": -2}
WORK_MODES = {"hybrid": 1, "remote": 1, "onsite": -2}
STAGES = {"startup": 0, "scale-up": 1, "enterprise": 0, "agency": -2}
DEMO_FACTS = {  # stage → (size class, founding year) of the employer record
    "startup": ("11-50", 2022), "scale-up": ("201-500", 2016),
    "enterprise": ("10,001+", 1978), "agency": ("11-50", 2012),
}
TOWNS = ["Northhaven", "Eastmere", "Brightwater Bay", "Fennick", "Oldmoor"]
HOME_TOWNS = TOWNS[:2]
STACK = ["kotlin", "java", "swift", "dart", "typescript", "python", "go", "csharp"]
TREES = ["Alder", "Birch", "Cedar", "Elm", "Fir", "Hazel", "Juniper", "Larch", "Maple", "Oak",
         "Pine", "Rowan", "Spruce", "Willow", "Yew", "Ash", "Beech", "Cypress", "Hawthorn",
         "Linden"]
NOTES = ["Commute would be long.", "Interesting product, vague role.", "Team size sounds right.",
         "Salary range missing.", "Would apply.", "Too much legacy code mentioned."]
TASKS = ["ship features end to end", "review code with the team",
         "work closely with design and product", "improve app performance and stability",
         "own the release process", "build offline-first features"]
PERKS = ["Flexible hours.", "A yearly learning budget.", "Four-day weeks in summer.",
         "A small, senior team.", "Regular hack days.", "Modern devices for testing."]

PROFILE = Profile(
    schema_version="1",
    summary="Mobile developer with five years of Android experience, mostly Kotlin, looking for "
            "product teams that build apps people use daily.",
    target_roles=["Android Developer", "Mobile Developer"],
    locations=HOME_TOWNS,
    remote="hybrid",
    seniority="mid",
)
POLICY_PACK = PolicyPack.model_validate({
    "schema_version": "1",
    "exclusion_rules": [
        {"id": "no-on-call", "field": "text", "operator": "contains_any",
         "value": ["24/7 on-call", "night shifts"]},
        {"id": "no-unpaid", "field": "title", "operator": "matches_regex",
         "value": r"(?i)\b(unpaid|volunteer)\b"},
        {"id": "no-betting", "field": "company", "operator": "equals",
         "value": "Demo Co. Lucky Spin"},
    ],
    "reason_chips": [
        {"id": "too-junior", "label": "Stelle zu junior", "polarity": "negative"},
        {"id": "too-senior", "label": "Stelle zu senior", "polarity": "negative"},
        {"id": "wrong-stack", "label": "falscher Tech-Stack", "polarity": "negative"},
        {"id": "onsite-only", "label": "nur vor Ort", "polarity": "negative"},
        {"id": "dull-domain", "label": "Branche uninteressant", "polarity": "negative"},
        # The positive chips mirror the negative ones in the same order.
        {"id": "fitting-seniority", "label": "passende Seniorität", "polarity": "positive"},
        {"id": "great-stack", "label": "passender Tech-Stack", "polarity": "positive"},
        {"id": "remote-possible", "label": "Remote möglich", "polarity": "positive"},
        {"id": "good-domain", "label": "spannende Branche", "polarity": "positive"},
    ],
    "feature_set": [
        {"id": "role_type", "description": "Kind of role", "type": "categorical",
         "options": ["android", "ios", "cross-platform", "backend", "qa", "game"]},
        {"id": "seniority", "description": "Seniority the posting asks for",
         "type": "categorical", "options": list(SENIORITY)},
        {"id": "domain", "description": "Product domain of the company", "type": "categorical",
         "options": list(DOMAINS)},
        {"id": "tech_stack", "description": "Languages the posting names", "type": "list",
         "options": STACK},
        {"id": "location", "description": "Town of the office", "type": "categorical",
         "options": TOWNS},
        {"id": "remote_option", "description": "Where the work happens", "type": "categorical",
         "options": list(WORK_MODES)},
        {"id": "company_stage", "description": "Stage of the company", "type": "categorical",
         "options": list(STAGES)},
    ],
})


def generate(root: Path = FIXTURE_DIRECTORY) -> None:
    """Write the demo persona data repository into `root`, replacing its postings and labels."""
    rng = random.Random(SEED)
    for name in ("postings", "labels", "companies"):
        shutil.rmtree(root / name, ignore_errors=True)
    _write(root / "profile.json", PROFILE)
    _write(root / "policy-pack.json", POLICY_PACK)

    companies = {f"Demo Co. {tree}": (rng.choice(list(DOMAINS)), rng.choice(list(STAGES)))
                 for tree in TREES}
    for name, (_, stage) in companies.items():
        size_class, founded = DEMO_FACTS[stage]
        write_company(root, company_id(name), Company(
            schema_version="1", name=name, size_class=size_class, founded=founded,
            source="linkedin", source_url=f"https://www.linkedin.com/company/{slug(name)}",
            fetched_at=START))
    excluded = set(rng.sample(range(IMPORTED, POSTING_COUNT - 10), 9))
    rated_discarded = 0
    rated: dict[str, tuple[Label, dict]] = {}
    for index in range(POSTING_COUNT):
        posting_id = f"demo-{index + 1:03d}"
        imported = index < IMPORTED
        company = rng.choice(list(companies))
        attributes = _attributes(rng, *companies[company])
        posting, utility = _posting(rng, index, company, attributes, imported)
        if index in excluded:
            posting = _make_excluded(posting, len(excluded & set(range(index))))
        label = None
        if imported:
            posting.legacy_decision = "kept" if utility + rng.gauss(0, 1) >= THRESHOLD else \
                "discarded"
            label = _imported_label(rng, posting, utility, index)
            if posting.legacy_decision == "discarded" and rated_discarded < 6 and \
                    label and label.kind == "imported_rejection":
                rated_discarded += 1
                posting.presented_at = START + timedelta(weeks=3 + rated_discarded % 3)
                label = _rating(rng, posting, attributes, utility)
        elif index not in excluded and index < POSTING_COUNT - 6:
            posting.presented_at = _next_run(posting.added_at)
            if index not in (140, 141):  # presented, but the run was lost before rating
                label = _rating(rng, posting, attributes, utility)
        _write(root / "postings" / f"{posting_id}.json", posting)
        if label:
            write_label(root, posting_id, label)
            if label.kind == "rating":
                rated[posting_id] = (label, attributes)
    _mix_one_rating(root, rated)


def _attributes(rng: random.Random, domain: str, stage: str) -> dict:
    title = rng.choice(list(ROLES))
    role_type, stack_choices, _ = ROLES[title]
    stack = sorted(rng.sample(stack_choices, rng.randint(1, len(stack_choices))), key=STACK.index)
    if rng.random() < 0.3:
        stack.append(rng.choice([s for s in STACK if s not in stack]))
    return {"title": title, "role_type": role_type, "stack": stack,
            "seniority": rng.choices(list(SENIORITY), weights=[2, 5, 4, 1])[0],
            "domain": domain, "stage": stage, "town": rng.choice(TOWNS),
            "mode": rng.choices(list(WORK_MODES), weights=[5, 3, 2])[0]}


def _utility(rng: random.Random, a: dict) -> float:
    location = 1 if a["mode"] == "remote" or a["town"] in HOME_TOWNS else -1
    return (ROLES[a["title"]][2] + SENIORITY[a["seniority"]] + DOMAINS[a["domain"]]
            + WORK_MODES[a["mode"]] + STAGES[a["stage"]] + ("kotlin" in a["stack"]) + location
            + rng.gauss(0, 1))


def _posting(rng: random.Random, index: int, company: str, a: dict, imported: bool):
    if imported:
        added_at = START + timedelta(hours=rng.randint(0, 10 * 24))
    else:
        added_at = START + timedelta(days=7 + (index - IMPORTED) * 77 / (POSTING_COUNT - IMPORTED),
                                     hours=rng.randint(0, 20))
    added_at = added_at.replace(minute=0, second=0, microsecond=0)
    prefix = "" if a["seniority"] == "mid" else f"{a['seniority'].capitalize()} "
    location = {"remote": "Remote", "hybrid": f"{a['town']} (hybrid)",
                "onsite": f"{a['town']}, on-site"}[a["mode"]]
    mode_text = {"remote": "fully remote within the country",
                 "hybrid": f"two office days a week in {a['town']}",
                 "onsite": f"on-site in our {a['town']} office"}[a["mode"]]
    tasks = rng.sample(TASKS, 3)
    article = "an" if a["stage"][0] in "aeiou" else "a"
    text = (f"{company} is {article} {a['stage']} building {a['domain']} apps. We are looking "
            f"for a {a['seniority']}-level {a['title']} to join our mobile team. "
            f"Work is {mode_text}.\n\n"
            f"Our stack: {', '.join(a['stack'])}. You will {tasks[0]}, {tasks[1]} and "
            f"{tasks[2]}.\n\n{rng.choice(PERKS)}")
    if a["seniority"] in ("senior", "lead"):
        text += " You will mentor less experienced colleagues."
    source_type = "url" if imported else rng.choices(["url", "text", "pdf"], [12, 5, 3])[0]
    urls = []
    if source_type == "url":
        urls = [rng.choice([f"https://jobs.example.com/postings/{index + 1:03d}",
                            f"https://careers.example.org/{company.split()[-1].lower()}/"
                            f"{index + 1:03d}"])]
    shown_company = "unknown" if source_type == "pdf" and rng.random() < 0.3 else company
    posting = Posting(
        schema_version="1", title=f"{prefix}{a['title']}", company=shown_company,
        location_raw=location, text=text, source_type=source_type, urls=urls, added_at=added_at,
        guard=Guard(flagged=False, categories=[], checked_by="demo-fixture", checked_at=added_at),
    )
    return posting, _utility(rng, a)


def _make_excluded(posting: Posting, nth: int) -> Posting:
    """Make the posting match one exclusion rule, cycling through the rules."""
    match nth % 3:
        case 0:
            posting.text += "\n\nThe role includes a 24/7 on-call rotation."
        case 1:
            posting.title = f"Unpaid {posting.title} Internship"
        case 2:
            posting.company = "Demo Co. Lucky Spin"
            posting.text = "Demo Co. Lucky Spin is " + posting.text.split(" is ", 1)[1]
    return posting


def _next_run(moment: datetime) -> datetime:
    """Weekly runs on Monday 18:00, starting in week 2."""
    week = max(1, (moment - START).days // 7 + 1)
    return START + timedelta(weeks=week, hours=9)


def _imported_label(rng: random.Random, posting: Posting, utility: float, index: int):
    if index % 10 == 9:
        return None
    rated_at = posting.added_at + timedelta(hours=rng.randint(1, 72))
    if index % 6 == 5:
        return Label(schema_version="1", kind="imported_not_preference", rated_at=rated_at)
    if posting.legacy_decision == "kept":
        return Label(schema_version="1", kind="imported_interest", verdict="positive",
                     rated_at=rated_at)
    return Label(schema_version="1", kind="imported_rejection", verdict="negative",
                 rated_at=rated_at)


def _reasons(a: dict, positive: bool) -> list[str]:
    """The chips of the given polarity that apply to a posting's attributes."""
    if positive:
        return [chip for chip, applies in (
            ("fitting-seniority", SENIORITY[a["seniority"]] > 0),
            ("great-stack", "kotlin" in a["stack"]), ("remote-possible", a["mode"] != "onsite"),
            ("good-domain", DOMAINS[a["domain"]] > 0),
        ) if applies]
    return [chip for chip, applies in (
        ("too-junior", a["seniority"] == "junior"), ("too-senior", a["seniority"] == "lead"),
        ("wrong-stack", "kotlin" not in a["stack"]), ("onsite-only", a["mode"] == "onsite"),
        ("dull-domain", DOMAINS[a["domain"]] < 0),
    ) if applies]


def _mix_one_rating(root: Path, rated: dict[str, tuple[Label, dict]]) -> None:
    """Give the earliest positive rating that has an applicable negative reason that reason as
    an extra chip, so one label mixes both polarities (a verdict a chip of the other polarity
    does not change). Draws no random numbers, so the rest of the fixture stays as it was."""
    for posting_id, (label, attributes) in sorted(rated.items(),
                                                  key=lambda item: item[1][0].rated_at):
        if label.verdict == "positive" and (negative := _reasons(attributes, False)):
            label.chips = sorted({*label.chips, negative[0]})
            write_label(root, posting_id, label)
            return


def _rating(rng: random.Random, posting: Posting, a: dict, utility: float) -> Label:
    positive = utility >= THRESHOLD
    reasons = _reasons(a, positive)
    chips = rng.sample(reasons, min(len(reasons), rng.choice([0, 1, 1, 2])))
    # The strength follows the margin to the threshold and draws no random numbers.
    strength = "strong" if abs(utility - THRESHOLD) >= STRONG_MARGIN else "weak"
    return Label(
        schema_version="1", kind="rating", verdict="positive" if positive else "negative",
        strength=strength, chips=sorted(chips),
        note=rng.choice(NOTES) if rng.random() < 0.2 else None,
        rated_at=posting.presented_at + timedelta(hours=rng.randint(1, 60)),
    )


def _write(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The fixture's postings stay at version 1, which has no `status`.
    exclude = {"status"} if isinstance(model, Posting) else None
    path.write_text(model.model_dump_json(indent=2, exclude_none=True, exclude=exclude) + "\n")


if __name__ == "__main__":
    generate()
