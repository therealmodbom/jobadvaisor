"""`score_posting`: the LLM judge's 0–10 score with reasoning, using rated examples."""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from jobadvaisor.data.models import PolicyPack, Posting, Profile
from jobadvaisor.tools.prompts import DATA_RULE, posting_block
from jobadvaisor.tools.similar import Example

INSTRUCTIONS = (
    "You judge how well one job posting fits the user, as an integer score from 0 (no fit) to "
    "10 (excellent fit), with a short reasoning. Rated postings similar to it show how the user "
    "decided before, with the reasons they gave; weigh them more than your own taste, and "
    "reference the IDs of the rated postings you compared it with in your reasoning. A rated "
    "posting can carry reasons of both kinds, positive and negative: when you compare with one, "
    "name each of its reasons that also holds for this posting, with the reason's label as "
    "written, and say which way it weighs. Write the "
    "reasoning in German, whatever language the posting is in, and keep the IDs as given.\n"
    + DATA_RULE.format(tag="posting") + "\n" + DATA_RULE.format(tag="example")
    + "\n\nThe user:\n{profile}"
)
NO_EXAMPLES = "No rated postings exist yet. Judge from the user's profile alone."


class ScoreResult(BaseModel):
    """What the judge returns through structured output."""

    score: int = Field(ge=0, le=10, description="Fit from 0 (none) to 10 (excellent)")
    reasoning: str = Field(description="Why, referencing the rated postings compared with")


@dataclass(frozen=True)
class Score:
    """A posting's score: 0–10, the judge's reasoning, and the IDs of the examples it was given
    (empty on a cold start)."""

    score: int
    reasoning: str
    example_ids: list[str]


def score_posting(posting: Posting, profile: Profile, policy_pack: PolicyPack,
                  examples: list[Example], model: BaseChatModel) -> Score:
    """Score `posting` for the user with the `judge` chat model.

    `examples` come from `find_similar_labeled`; each reaches the judge with its verdict, reason
    chip labels and note, its posting text inside an `<example>` data block. With no examples,
    the judge scores from the profile alone. Raises whatever structured output raises for an
    answer outside `ScoreResult`.
    """
    instructions, message = scoring_prompt(posting, profile, policy_pack, examples)
    result = model.with_structured_output(ScoreResult).invoke([
        SystemMessage(instructions), HumanMessage(message)])
    return Score(result.score, result.reasoning, [example.posting_id for example in examples])


def scoring_prompt(posting: Posting, profile: Profile, policy_pack: PolicyPack,
                   examples: list[Example]) -> tuple[str, str]:
    """The judge's instructions (with the profile) and its message: the rated examples, then
    "Posting to score:" and the posting's data block, last. The decision-model competitor
    sends the same text."""
    chips = {chip.id: f"{chip.polarity}: {chip.label}" if chip.polarity else chip.label
             for chip in policy_pack.reason_chips}
    shown = "\n\n".join(_example(example, chips) for example in examples) or NO_EXAMPLES
    return (INSTRUCTIONS.format(profile=_profile(profile)),
            f"Rated postings:\n\n{shown}\n\nPosting to score:\n{posting_block(posting)}")


def _profile(profile: Profile) -> str:
    lines = [profile.summary, f"Target roles: {', '.join(profile.target_roles) or 'any'}",
             f"Locations: {', '.join(profile.locations) or 'any'}",
             f"Work mode: {profile.remote}", f"Seniority: {profile.seniority or 'any'}"]
    return "\n".join(lines)


def _example(example: Example, chips: dict[str, str]) -> str:
    label = example.label
    reasons = "; ".join(chips.get(chip, chip) for chip in label.chips) or "none given"
    note = f"; note: {label.note}" if label.note else ""
    strength = f" ({label.strength})" if label.strength else ""
    return (f"Rated posting {example.posting_id}: {label.verdict}{strength}; "
            f"reasons: {reasons}{note}\n"
            f"{posting_block(example.posting, 'example')}")
