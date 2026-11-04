"""`find_similar_labeled`: the rated postings most similar to a posting, as scoring examples."""

from dataclasses import dataclass
from datetime import datetime

from jobadvaisor.data.loader import DataRepository
from jobadvaisor.data.models import Label, Posting
from jobadvaisor.index import LabelIndex, embedding_text
from jobadvaisor.tools.guard import ContentGuard


@dataclass(frozen=True)
class Example:
    """A labeled posting used as a scoring example."""

    posting_id: str
    posting: Posting
    label: Label


def find_similar_labeled(guard: ContentGuard, index: LabelIndex, repository: DataRepository,
                         posting: Posting, k: int = 5, rated_before: datetime | None = None,
                         posting_id: str | None = None) -> list[Example]:
    """Up to `k` labeled postings nearest to `posting`, nearest first, from a synced `index`.

    Examples reach a model, so `guard` applies each one's stored guard result (screening an
    unscreened one) and withheld examples are left out. `rated_before` keeps only labels rated
    strictly before it (the eval time split). `posting_id`, the posting's own ID if it is
    stored, keeps it from being its own example.
    """
    # ponytail: fetches 2k+1 candidates, so more than k+1 withheld neighbours shrink the result
    nearest = index.nearest(embedding_text(posting), 2 * k + 1, rated_before)
    examples = []
    for found in nearest:
        if found != posting_id and (shown := guard.posting(repository, found)) is not None:
            examples.append(Example(found, shown, repository.labels[found]))
    return examples[:k]
