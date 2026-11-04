import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from chromadb.api.client import SharedSystemClient
from conftest import LABEL, POSTING, write_json
from langchain_core.embeddings import DeterministicFakeEmbedding

from jobadvaisor.data.loader import load
from jobadvaisor.data.models import Posting
from jobadvaisor.index import LabelIndex, PostingIndex, state_path
from jobadvaisor.settings import Settings
from jobadvaisor.tools.guard import ContentGuard
from jobadvaisor.tools.similar import find_similar_labeled


class CountingEmbedding(DeterministicFakeEmbedding):
    embedded: int = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embedded += len(texts)
        return super().embed_documents(texts)


GUARD = ContentGuard(None, {})  # screening off: only stored clean guards pass
CLEAN = {"flagged": False, "checked_by": "test", "checked_at": "2026-01-05T09:00:00Z"}


@pytest.fixture
def repository_root(data_repository: Path) -> Path:
    """The shared fixture, all postings screened clean, plus labeled `p3` (rated later), `p4`
    (imported_not_preference) and unlabeled `p5`."""
    for posting_id, title in (("p1", POSTING["title"]), ("p2", "Data Engineer"),
                              ("p3", "Android Developer"), ("p4", "iOS Developer"),
                              ("p5", "QA Engineer")):
        write_json(data_repository / f"postings/{posting_id}.json",
                   {**POSTING, "title": title, "guard": CLEAN})
    write_json(data_repository / "labels/p3.json", {**LABEL, "rated_at": "2026-02-01T09:00:00Z"})
    write_json(data_repository / "labels/p4.json", {"schema_version": "1",
                                                     "kind": "imported_not_preference",
                                                     "rated_at": "2026-01-05T09:00:00Z"})
    return data_repository


def query() -> Posting:
    return Posting.model_validate({**POSTING, "title": "Mobile Developer"})


def ids(examples) -> list[str]:
    return [example.posting_id for example in examples]


def built_index(directory: Path, root: Path, embedding=None, model="fake-16") -> LabelIndex:
    index = LabelIndex(directory, embedding or DeterministicFakeEmbedding(size=16), model)
    index.sync(load(root))
    return index


def test_another_embedding_model_rebuilds_the_index(tmp_path, repository_root):
    built_index(tmp_path / "chroma", repository_root)
    embedding = CountingEmbedding(size=32)
    reopened = LabelIndex(tmp_path / "chroma", embedding, "fake-32")
    assert reopened.posting_ids() == []
    reopened.sync(load(repository_root))
    assert sorted(reopened.posting_ids()) == ["p1", "p3"] and embedding.embedded == 2
    assert find_similar_labeled(GUARD, reopened, load(repository_root), query(), k=5)


def test_only_labels_with_a_verdict_are_indexed(tmp_path, repository_root):
    index = built_index(tmp_path / "chroma", repository_root)
    assert sorted(index.posting_ids()) == ["p1", "p3"]


def test_examples_carry_posting_and_label(tmp_path, repository_root):
    repository = load(repository_root)
    examples = find_similar_labeled(GUARD, built_index(tmp_path / "chroma", repository_root),
                                    repository, query(), k=5)
    assert sorted(ids(examples)) == ["p1", "p3"]
    assert all(example.label == repository.labels[example.posting_id] and
               example.posting == repository.postings[example.posting_id]
               for example in examples)


def test_deleting_the_index_changes_no_retrieval_result(tmp_path, repository_root):
    repository = load(repository_root)
    before = find_similar_labeled(GUARD, built_index(tmp_path / "chroma", repository_root),
                                  repository, query(), k=5)
    shutil.rmtree(tmp_path / "chroma")
    # A deleted index is rebuilt by the next process; Chroma keeps per-path state for the
    # process's lifetime, and reusing it after the delete fails now and then (code 14).
    SharedSystemClient.clear_system_cache()
    after = find_similar_labeled(GUARD, built_index(tmp_path / "chroma", repository_root),
                                 repository, query(), k=5)
    assert ids(after) == ids(before) and len(before) == 2


def test_sync_adds_new_labels_and_drops_removed_ones_without_re_embedding(tmp_path,
                                                                          repository_root):
    embedding = CountingEmbedding(size=16)
    index = built_index(tmp_path / "chroma", repository_root, embedding)
    assert embedding.embedded == 2
    write_json(repository_root / "labels/p5.json", LABEL)
    (repository_root / "labels/p3.json").unlink()
    index.sync(load(repository_root))
    assert sorted(index.posting_ids()) == ["p1", "p5"]
    assert embedding.embedded == 3


def test_label_turned_imported_not_preference_leaves_the_index(tmp_path, repository_root):
    index = built_index(tmp_path / "chroma", repository_root)
    write_json(repository_root / "labels/p3.json", {"schema_version": "1",
                                                     "kind": "imported_not_preference",
                                                     "rated_at": "2026-02-01T09:00:00Z"})
    index.sync(load(repository_root))
    assert index.posting_ids() == ["p1"]


def test_rated_before_excludes_labels_at_or_after_the_cut_off(tmp_path, repository_root):
    repository = load(repository_root)
    index = built_index(tmp_path / "chroma", repository_root)
    cut_off = datetime(2026, 2, 1, 9, tzinfo=UTC)
    assert ids(find_similar_labeled(GUARD, index, repository, query(), k=5,
                                    rated_before=cut_off)) == ["p1"]


def test_the_posting_itself_is_never_its_own_example(tmp_path, repository_root):
    repository = load(repository_root)
    examples = find_similar_labeled(GUARD, built_index(tmp_path / "chroma", repository_root),
                                    repository, repository.postings["p1"], k=1,
                                    posting_id="p1")
    assert ids(examples) == ["p3"]


@pytest.mark.parametrize("guard", [{**CLEAN, "flagged": True, "categories": ["jailbreaking"]},
                                   None])
def test_examples_the_guard_withholds_are_left_out(tmp_path, repository_root, guard):
    write_json(repository_root / "postings/p3.json", {**POSTING, "title": "Android Developer",
                                                      **({"guard": guard} if guard else {})})
    repository = load(repository_root)
    examples = find_similar_labeled(GUARD, built_index(tmp_path / "chroma", repository_root),
                                    repository, query(), k=5)
    assert ids(examples) == ["p1"]


def test_empty_index_returns_no_examples(tmp_path, data_repository):
    (data_repository / "labels/p1.json").unlink()
    repository = load(data_repository)
    index = built_index(tmp_path / "chroma", data_repository)
    assert find_similar_labeled(GUARD, index, repository, query(), k=5) == []


def test_state_path_is_outside_the_repository_and_unique_per_data_repository(tmp_path):
    settings = Settings(_env_file=None)
    assert settings.state_directory == Path.home() / ".jobadvaisor"
    first, second = tmp_path / "a" / "data", tmp_path / "b" / "data"
    paths = {state_path(settings, first), state_path(settings, second)}
    assert len(paths) == 2
    assert all(path.parent == settings.state_directory and path.name.startswith("data-")
               for path in paths)


def test_posting_index_holds_every_stored_posting_and_follows_changes(tmp_path, repository_root):
    embedding = CountingEmbedding(size=16)
    index = PostingIndex(tmp_path / "chroma", embedding, "fake-16")
    index.sync(load(repository_root))
    assert sorted(index.posting_ids()) == ["p1", "p2", "p3", "p4", "p5"]
    assert index.nearest("QA Engineer\n\nWe build things.", 1) == ["p5"]
    (repository_root / "postings/p5.json").unlink()
    write_json(repository_root / "postings/p2.json", {**POSTING, "title": "Data Lead"})
    embedded = embedding.embedded
    index.sync(load(repository_root))
    assert sorted(index.posting_ids()) == ["p1", "p2", "p3", "p4"]
    assert embedding.embedded == embedded + 1
