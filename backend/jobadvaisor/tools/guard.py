"""The tool-boundary wrapper every text-returning tool uses (`design.md` → Content guard)."""

from jobadvaisor.data.loader import DataRepository
from jobadvaisor.data.models import Guard, Posting
from jobadvaisor.data.writer import write_guard
from jobadvaisor.guard import Classifier, classifier_from_settings, screen_content
from jobadvaisor.settings import Settings

WITHHELD = "content withheld by the content guard"


class ContentGuard:
    """Screens third-party text and applies stored postings' guard results before any text
    reaches a model. `classifier` is `None` when screening is off."""

    def __init__(self, classifier: Classifier | None, thresholds: dict[str, float]):
        self.classifier, self.thresholds = classifier, thresholds

    def screen(self, text: str) -> Guard:
        """The guard result for `text`. Only call with a classifier configured."""
        return screen_content(text, self.classifier, self.thresholds)

    def third_party(self, text: str) -> str:
        """Fetched text as a model may see it: `WITHHELD` when flagged; unchanged when clean or
        when screening is off (the structural defenses still apply)."""
        if self.classifier is None:
            return text
        return WITHHELD if self.screen(text).flagged else text

    def posting(self, repository: DataRepository, posting_id: str) -> Posting | None:
        """The stored posting if a model may see its text, else `None` (show `WITHHELD`).

        A stored `guard` is applied as is: flagged and not released withholds. A posting
        without `guard` is screened now and the result written to the data repository and to
        `repository`; with screening off it is withheld and nothing is written.
        """
        posting = repository.postings[posting_id]
        if posting.guard is None:
            if self.classifier is None:
                return None
            guard = self.screen(screened_text(posting))
            posting = write_guard(repository.root, posting_id, guard)
            repository.postings[posting_id] = posting
        guard = posting.guard
        return None if guard.flagged and guard.released_at is None else posting


def content_guard(settings: Settings) -> ContentGuard:
    """The configured guard (`classifier_from_settings`) with `GUARD_THRESHOLDS`, or with the
    classifier's own defaults when that is unset; screening off without a classifier."""
    classifier = classifier_from_settings(settings)
    thresholds = settings.guard_thresholds or (classifier.thresholds if classifier else {})
    return ContentGuard(classifier, thresholds)


def screened_text(posting: Posting) -> str:
    """Every third-party field of a posting, as one text for the classifier."""
    return f"{posting.title}\n{posting.company}\n{posting.location_raw}\n\n{posting.text}"
