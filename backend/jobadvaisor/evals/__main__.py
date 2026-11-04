"""`python -m jobadvaisor.evals [--data PATH] [--out DIR] [--only NAME ...]`

Runs the evals against a data repository (default: the demo persona), prints one JSON report
per eval, and writes them to `--out` when given. Results from data other than the demo persona
are always written, by default to `<STATE_DIRECTORY>/<repository key>/evals/`, and never inside
this repository.
"""

import argparse
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import DataRepository, load
from jobadvaisor.evals import (
    agent,
    baseline,
    company_facts,
    content_guard,
    feature_extraction,
    field_filling,
    graph_vs_agent,
    intake,
    logistic,
    scoring,
)
from jobadvaisor.evals import decider as decider_competitor
from jobadvaisor.guard import MISTRAL_MODEL, DeciderClassifier, MistralModeration
from jobadvaisor.index import LabelIndex, PostingIndex, state_path
from jobadvaisor.llm import ModelNotConfiguredError, chat_model, decider, embeddings
from jobadvaisor.settings import REPOSITORY_ROOT, Settings
from jobadvaisor.tools.guard import content_guard as configured_guard

Eval = Callable[[DataRepository, Settings], dict]


def _synced_index(repository: DataRepository, settings: Settings) -> LabelIndex:
    """The repository's label index under the state directory, synced with its labels."""
    index = LabelIndex(state_path(settings, repository.root) / "chroma", embeddings(settings),
                       settings.embedding_model)
    index.sync(repository)
    return index


def _scoring(repository: DataRepository, settings: Settings) -> dict:
    """Sync the repository's label index under the state directory, then run the scoring eval."""
    index = _synced_index(repository, settings)
    report = scoring.run(repository, index, configured_guard(settings),
                         chat_model("judge", settings), settings.judge_model or settings.llm_model)
    return report | {"embedding_model": settings.embedding_model}


def _graph_vs_agent(repository: DataRepository, settings: Settings) -> dict:
    """Graph versus agent, with one label index for the time-split copies under the state
    directory, kept apart from the full index so neither re-embeds the other's postings."""
    embedder = embeddings(settings)
    models = {role: getattr(settings, f"{role}_model") or settings.llm_model
              for role in ("extractor", "judge", "agent")}
    directory = state_path(settings, repository.root) / "chroma-time-split"
    report = graph_vs_agent.run(
        repository, configured_guard(settings),
        lambda root: (LabelIndex(directory, embedder, settings.embedding_model),
                      PostingIndex(directory, embedder, settings.embedding_model)),
        chat_model("extractor", settings), chat_model("judge", settings),
        chat_model("agent", settings))
    return report | {"models": models, "embedding_model": settings.embedding_model}


def _agent(repository: DataRepository, settings: Settings) -> dict:
    """The agent eval over both synced indexes under the state directory."""
    postings = PostingIndex(state_path(settings, repository.root) / "chroma",
                            embeddings(settings), settings.embedding_model)
    postings.sync(repository)
    return agent.run(repository, _synced_index(repository, settings), postings,
                     configured_guard(settings), chat_model("agent", settings),
                     chat_model("extractor", settings), chat_model("judge", settings),
                     settings.agent_model or settings.llm_model)


def _decider_competitor(repository: DataRepository, settings: Settings) -> dict:
    """The decision-model competitor, skipped without `DECIDER_MODEL` before any index work."""
    chosen = decider(settings)
    if chosen is None:
        return decider_competitor.run(repository, None, None, None)
    return decider_competitor.run(repository, _synced_index(repository, settings),
                                  configured_guard(settings), chosen)


def _content_guard(repository: DataRepository, settings: Settings) -> dict:
    """The content-guard eval for Mistral Moderation and the decision model, each with its own
    default thresholds and skipped with its reason when not configured."""
    chosen = decider(settings)
    classifiers = [
        (MistralModeration(settings.mistral_api_key) if settings.mistral_api_key else None,
         {"classifier": MISTRAL_MODEL, "skipped": "MISTRAL_API_KEY is not set"}),
        (DeciderClassifier(chosen) if chosen else None,
         {"classifier": "decider", "skipped": "DECIDER_MODEL is not set"})]
    rows = [content_guard.run(repository, classifier, classifier.thresholds) if classifier
            else skipped for classifier, skipped in classifiers]
    return {"eval": "content_guard", "classifiers": rows}


EVALS: dict[str, Eval] = {
    "feature_extraction": lambda repository, settings: feature_extraction.run(
        repository, chat_model("extractor", settings),
        settings.extractor_model or settings.llm_model),
    "company_facts": lambda repository, settings: company_facts.run(
        repository, chat_model("extractor", settings),
        settings.extractor_model or settings.llm_model),
    "scoring": _scoring,
    "baseline": lambda repository, settings: baseline.run(repository),
    "content_guard": _content_guard,
    "intake": lambda repository, settings: intake.run(
        lambda target: chat_model("intake", settings), configured_guard(settings),
        settings.intake_model or settings.llm_model),
    "field_filling": lambda repository, settings: field_filling.run(
        repository, chat_model("intake", settings), settings.intake_model or settings.llm_model),
    "logistic_regression": lambda repository, settings: logistic.run(
        repository, configured_guard(settings), chat_model("extractor", settings),
        settings.extractor_model or settings.llm_model,
        minimum_labels=settings.competitor_min_labels),
    "agent": _agent,
    "graph_vs_agent": _graph_vs_agent,
    "decider_competitor": _decider_competitor,
}


def _run(name: str, repository: DataRepository, settings: Settings) -> dict:
    """One eval's report, its skip reason when a model it needs is not configured, or its error,
    so one failing eval never discards the reports of the others."""
    try:
        return EVALS[name](repository, settings)
    except ModelNotConfiguredError as error:
        return {"eval": name, "skipped": str(error)}
    except Exception as error:  # report it and go on to the next eval
        return {"eval": name, "error": f"{type(error).__name__}: {error}"}


def main(argv: list[str] | None = None) -> None:
    """Parse `argv`, run the selected evals and print their reports as a JSON list."""
    parser = argparse.ArgumentParser(prog="python -m jobadvaisor.evals")
    parser.add_argument("--data", type=Path, default=FIXTURE_DIRECTORY)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--only", nargs="+", choices=list(EVALS), default=list(EVALS))
    args = parser.parse_args(argv)
    settings = Settings()
    out = args.out
    if args.data.resolve() != FIXTURE_DIRECTORY.resolve():
        out = out or state_path(settings, args.data) / "evals"
        if out.resolve().is_relative_to(REPOSITORY_ROOT):
            parser.error(f"reports for data other than the demo persona must lie outside this "
                         f"repository; {out} does not (set --out or STATE_DIRECTORY)")
    repository = load(args.data)
    reports = [_run(name, repository, settings) for name in args.only]
    text = json.dumps(reports, indent=2, ensure_ascii=False)
    print(text)
    if out:
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        (out / f"evals-{stamp}.json").write_text(text + "\n")


if __name__ == "__main__":
    main()
