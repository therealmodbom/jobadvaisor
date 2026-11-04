"""Feature extraction with structured output over the configurable feature set."""

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, create_model

from jobadvaisor.data.models import Company, Feature, Posting
from jobadvaisor.tools.prompts import DATA_RULE, company_facts_block, posting_block

UNKNOWN = "unknown"

DEFAULT_FEATURE_SET = [
    Feature(id="role_type", description="Kind of role, e.g. backend engineering", type="text"),
    Feature(id="seniority", description="Seniority the posting asks for", type="categorical",
            options=["junior", "mid", "senior", "lead"]),
    Feature(id="domain", description="Product domain or industry of the company", type="text"),
    Feature(id="tech_stack", description="Languages and technologies the posting names, "
                                         "comma-separated", type="text"),
    Feature(id="location", description="Office location the posting names", type="text"),
    Feature(id="remote_option", description="Where the work happens", type="categorical",
            options=["onsite", "hybrid", "remote"]),
    Feature(id="company_stage", description="Stage of the company", type="categorical",
            options=["startup", "scale-up", "enterprise", "agency"]),
]

INSTRUCTIONS = (
    "You extract features from one job posting. For each feature below, answer with a value the "
    "posting supports, or \"unknown\" when it does not say. Never guess beyond the posting.\n"
    + DATA_RULE.format(tag="posting") + "\n\nFeatures:\n{features}"
)
FACTS_RULE = (
    "The <company_facts> block comes from a lookup about the employer or an entry by hand, as "
    "its last sentence says; the text in <posting> comes from the posting. Where the posting "
    "states the company's size or stage, the posting decides company_stage; where it does not, "
    "take company_stage from the facts (size class and founding year) instead of answering "
    "unknown."
)


def feature_set(configured: list[Feature]) -> list[Feature]:
    """The features to extract: the defaults, each replaced by a configured feature of the same
    ID, followed by the configured features with new IDs, in their configured order."""
    by_id = {feature.id: feature for feature in configured}
    default_ids = {feature.id for feature in DEFAULT_FEATURE_SET}
    return ([by_id.get(feature.id, feature) for feature in DEFAULT_FEATURE_SET]
            + [feature for feature in configured if feature.id not in default_ids])


def result_model(features: list[Feature]) -> type[BaseModel]:
    """A Pydantic model with one required field per feature, named by its ID (as alias, since
    an ID need not be a Python identifier), accepting the feature's values or "unknown"."""
    fields = {f"feature_{index}": (_annotation(feature), Field(alias=feature.id,
                                                               description=feature.description))
              for index, feature in enumerate(features)}
    return create_model("ExtractedFeatures", **fields)


def extract_features(posting: Posting, features: list[Feature], model: BaseChatModel,
                     facts: Company | None = None) -> dict:
    """Feature ID → extracted value or "unknown", for every feature in `features`.

    `model` is the `extractor` chat model; the posting reaches it only as a data block. `facts`
    is the posting company's stored record: when it holds a size class or a founding year they
    follow as a `<company_facts>` block of their own and the instructions say where they come
    from; without them the call is the one made before company facts existed. Raises whatever
    the model's structured output raises for an answer outside the result model.
    """
    system = INSTRUCTIONS.format(features="\n".join(map(_describe, features)))
    human = posting_block(posting)
    if facts and (block := company_facts_block(facts)):
        system += "\n\n" + FACTS_RULE
        human += "\n\n" + block
    structured = model.with_structured_output(result_model(features))
    result = structured.invoke([SystemMessage(system), HumanMessage(human)])
    return result.model_dump(by_alias=True)


def _annotation(feature: Feature) -> Any:
    unknown = Literal[UNKNOWN]
    match feature.type:
        case "categorical":
            return Literal[tuple(feature.options) + (UNKNOWN,)]
        case "list":
            return list[Literal[tuple(feature.options)]] | unknown
        case "boolean":
            return bool | unknown
        case "number":
            return float | unknown
        case "text":
            return str


def _describe(feature: Feature) -> str:
    allowed = {"categorical": f"one of {feature.options}",
               "list": f"a list drawn from {feature.options}", "boolean": "true or false",
               "number": "a number", "text": "a short text"}[feature.type]
    return f"- {feature.id}: {feature.description} ({allowed}, or \"unknown\")"
