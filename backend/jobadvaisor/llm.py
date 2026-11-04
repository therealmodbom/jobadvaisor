"""Model clients per role, built from `Settings` (`design.md` → Models configured per role).

A model name without a `provider:` prefix is sent to an OpenAI-compatible endpoint when a base
URL is set, so router names such as `openai/gpt-5.4-mini` work as they are. `LLM_API_KEY`, when
set, is the key of every client; without it, each provider package reads its own variable.
"""

from dataclasses import dataclass
from functools import cache
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from openai import OpenAI

from jobadvaisor.settings import Settings

Role = Literal["extractor", "judge", "intake", "agent"]


class ModelNotConfiguredError(Exception):
    """A model was requested whose settings are unset; the message names them."""


@dataclass(frozen=True)
class Decider:
    """The decision model (`design.md` → Decision models): an OpenAI client and the pinned model,
    called directly since LangChain has no binding for its response format (ADR 0003)."""

    client: OpenAI
    model: str


def chat_model(role: Role, settings: Settings) -> BaseChatModel:
    """Chat model for `role`: `<ROLE>_MODEL` / `<ROLE>_BASE_URL`, each falling back to
    `LLM_MODEL` / `LLM_BASE_URL`, with Langfuse tracing attached when configured.

    Raises `ModelNotConfiguredError` when neither model setting is set.
    """
    model = getattr(settings, f"{role}_model") or settings.llm_model
    if not model:
        raise ModelNotConfiguredError(f"{role.upper()}_MODEL or LLM_MODEL is not set")
    base_url = getattr(settings, f"{role}_base_url") or settings.llm_base_url
    return model_client(model, base_url, settings)


def model_client(model: str, base_url: str | None, settings: Settings) -> BaseChatModel:
    """Chat model for an explicit `model` / `base_url` pair (e.g. one benchmark run), built under
    the same provider-prefix and connection rules as `chat_model`; `settings` supplies the API
    key and Langfuse tracing."""
    return init_chat_model(model, model_provider=_provider(model, base_url),
                           callbacks=tracing(settings) or None,
                           **_connection(base_url, settings.llm_api_key))


def embeddings(settings: Settings) -> Embeddings:
    """Embedding model from `EMBEDDING_MODEL`, through `LLM_BASE_URL` when set.

    Behind a base URL, texts are sent as strings: OpenAI's client would otherwise send tiktoken
    token IDs, which a router serving other providers' models need not accept. Raises
    `ModelNotConfiguredError` when `EMBEDDING_MODEL` is unset.
    """
    model = settings.embedding_model
    if not model:
        raise ModelNotConfiguredError("EMBEDDING_MODEL is not set")
    base_url = settings.llm_base_url
    extra = {"check_embedding_ctx_length": False} if base_url else {}
    return init_embeddings(model, provider=_provider(model, base_url),
                           **_connection(base_url, settings.llm_api_key), **extra)


def guard_model(settings: Settings) -> Decider | None:
    """The content guard's classifier model from `GUARD_MODEL` and `GUARD_BASE_URL` (falling back
    to `LLM_BASE_URL`), called in the router's `questions` format; `None` when `GUARD_MODEL` is
    unset."""
    if not settings.guard_model:
        return None
    return decider_client(settings.guard_model,
                          settings.guard_base_url or settings.llm_base_url, settings)


def decider_client(model: str, base_url: str | None, settings: Settings) -> Decider:
    """The decision model `model` reached at `base_url` with the app's API key, for one explicit
    (model, base URL) pair (e.g. one benchmark run)."""
    return Decider(OpenAI(**_connection(base_url, settings.llm_api_key)), model)


def tracing(settings: Settings) -> list[BaseCallbackHandler]:
    """Langfuse callback handlers for every model call: one with both Langfuse keys, else none."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return []
    return [_langfuse_handler(settings.langfuse_public_key, settings.langfuse_secret_key,
                              settings.langfuse_base_url)]


@cache
def _langfuse_handler(public_key: str, secret_key: str, base_url: str | None):
    """One client and handler per key set; the client is registered under its public key."""
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler

    Langfuse(public_key=public_key, secret_key=secret_key, base_url=base_url)
    return CallbackHandler(public_key=public_key)


def _provider(model: str, base_url: str | None) -> str | None:
    return "openai" if base_url and ":" not in model else None


def _connection(base_url: str | None, api_key: str | None) -> dict[str, str]:
    return {name: value for name, value in (("base_url", base_url), ("api_key", api_key))
            if value}
