"""The vector index of labeled postings (`design.md` → Vector index), rebuildable at any time
from the data repository."""

import hashlib
import re
from datetime import datetime
from pathlib import Path

import chromadb
from langchain_core.embeddings import Embeddings

from jobadvaisor.data.loader import DataRepository
from jobadvaisor.data.models import Posting
from jobadvaisor.settings import Settings

COLLECTION = "labeled_postings"
POSTINGS_COLLECTION = "postings"


def state_path(settings: Settings, data_repository: Path) -> Path:
    """This data repository's directory for local stores: `<STATE_DIRECTORY>/<name>-<hash>`,
    the hash taken over the resolved path, so two repositories never share stores."""
    resolved = data_repository.resolve()
    digest = hashlib.sha256(str(resolved).encode()).hexdigest()[:10]
    name = re.sub(r"[^A-Za-z0-9._-]", "_", resolved.name) or "root"
    return settings.state_directory / f"{name}-{digest}"


def embedding_text(posting: Posting) -> str:
    """What gets embedded for a posting: its title plus its text."""
    return f"{posting.title}\n\n{posting.text}"


class LabelIndex:
    """Chroma collection of labeled postings under `directory`, created when missing.

    Records hold the embedding of `embedding_text`, a hash of that text and `rated_at` (epoch
    seconds, for the eval cut-off). Labels of kind `imported_not_preference` are never indexed.
    `embedding_model` names the model behind `embeddings`; a collection built with another one
    is dropped, so vectors of two models never mix. Chroma's anonymized telemetry is off.
    """

    def __init__(self, directory: Path, embeddings: Embeddings, embedding_model: str):
        self._collection = _collection(directory, COLLECTION, embedding_model)
        self._embeddings = embeddings

    def sync(self, repository: DataRepository) -> None:
        """Make the index match the repository's usable labels: embed postings that are missing
        or whose text changed, update a changed `rated_at`, and drop records without a usable
        label."""
        wanted = {posting_id: (repository.postings[posting_id], label)
                  for posting_id, label in repository.labels.items()
                  if label.kind != "imported_not_preference"}
        stored = self._collection.get(include=["metadatas"])
        current = dict(zip(stored["ids"], stored["metadatas"], strict=True))
        if gone := [posting_id for posting_id in current if posting_id not in wanted]:
            self._collection.delete(ids=gone)
        embed, update = [], []
        for posting_id, (posting, label) in wanted.items():
            metadata = {"text_hash": _hash(embedding_text(posting)),
                        "rated_at": label.rated_at.timestamp()}
            if posting_id not in current or current[posting_id]["text_hash"] != metadata[
                    "text_hash"]:
                embed.append((posting_id, embedding_text(posting), metadata))
            elif current[posting_id] != metadata:
                update.append((posting_id, metadata))
        if embed:
            posting_ids, texts, metadatas = map(list, zip(*embed, strict=True))
            self._collection.upsert(ids=posting_ids, metadatas=metadatas,
                                    embeddings=self._embeddings.embed_documents(texts))
        if update:
            posting_ids, metadatas = map(list, zip(*update, strict=True))
            self._collection.update(ids=posting_ids, metadatas=metadatas)

    def posting_ids(self) -> list[str]:
        """IDs of every indexed posting, in no particular order."""
        return self._collection.get(include=[])["ids"]

    def nearest(self, text: str, k: int, rated_before: datetime | None = None) -> list[str]:
        """IDs of up to `k` indexed postings most similar to `text`, nearest first, only labels
        rated strictly before `rated_before` when given."""
        if k < 1 or self._collection.count() == 0:
            return []
        where = {"rated_at": {"$lt": rated_before.timestamp()}} if rated_before else None
        result = self._collection.query(query_embeddings=[self._embeddings.embed_query(text)],
                                        n_results=k, where=where, include=[])
        return result["ids"][0]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class PostingIndex:
    """Chroma collection of every stored posting, rated or not, under `directory`, for
    "postings like this one" (decision, 2026-10-11). Kept apart from `LabelIndex`, whose
    records are scoring examples. Records hold the embedding of `embedding_text` and its hash;
    a collection built with another `embedding_model` is dropped."""

    def __init__(self, directory: Path, embeddings: Embeddings, embedding_model: str):
        self._collection = _collection(directory, POSTINGS_COLLECTION, embedding_model)
        self._embeddings = embeddings

    def sync(self, repository: DataRepository) -> None:
        """Make the index match the repository's postings: embed new or changed ones and drop
        removed ones."""
        stored = self._collection.get(include=["metadatas"])
        current = dict(zip(stored["ids"], stored["metadatas"], strict=True))
        if gone := [posting_id for posting_id in current if posting_id not in repository.postings]:
            self._collection.delete(ids=gone)
        embed = [(posting_id, embedding_text(posting))
                 for posting_id, posting in repository.postings.items()
                 if current.get(posting_id, {}).get("text_hash") != _hash(embedding_text(posting))]
        if embed:
            posting_ids, texts = map(list, zip(*embed, strict=True))
            self._collection.upsert(ids=posting_ids,
                                    metadatas=[{"text_hash": _hash(text)} for text in texts],
                                    embeddings=self._embeddings.embed_documents(texts))

    def posting_ids(self) -> list[str]:
        """IDs of every indexed posting, in no particular order."""
        return self._collection.get(include=[])["ids"]

    def nearest(self, text: str, k: int) -> list[str]:
        """IDs of up to `k` indexed postings most similar to `text`, nearest first."""
        if k < 1 or self._collection.count() == 0:
            return []
        return self._collection.query(query_embeddings=[self._embeddings.embed_query(text)],
                                      n_results=k, include=[])["ids"][0]


def _collection(directory: Path, name: str, embedding_model: str):
    """The Chroma collection `name` under `directory` (cosine distance, telemetry off), dropped
    and recreated when it was built with another embedding model."""
    client = chromadb.PersistentClient(
        path=str(directory), settings=chromadb.Settings(anonymized_telemetry=False))
    metadata = {"hnsw:space": "cosine", "embedding_model": embedding_model}
    collection = client.get_or_create_collection(name, metadata=metadata, embedding_function=None)
    if (collection.metadata or {}).get("embedding_model") != embedding_model:
        client.delete_collection(name)
        collection = client.create_collection(name, metadata=metadata, embedding_function=None)
    return collection
