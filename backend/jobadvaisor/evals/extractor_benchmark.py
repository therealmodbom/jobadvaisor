"""Extractor benchmark: `python -m jobadvaisor.evals.extractor_benchmark` (`openspec/changes/
extractor-benchmark`). One run evaluates one extraction approach on the stored postings and stores
the run; stored runs are compared, and the disagreements settled into extraction labels.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from langchain_core.language_models import BaseChatModel
from langfuse import Evaluation, Langfuse

from jobadvaisor.data.demo_persona import FIXTURE_DIRECTORY
from jobadvaisor.data.loader import DataRepository, DataRepositoryError, load
from jobadvaisor.data.models import Company, Feature, Posting
from jobadvaisor.data.writer import merge_extraction_labels
from jobadvaisor.evals.cost import metered
from jobadvaisor.evals.decider import choice_question, extract_choices
from jobadvaisor.evals.deepeval_runtime import DeepEval, load_deepeval
from jobadvaisor.evals.extraction_accuracy import ACCURACY, pooled_accuracy, score_accuracy
from jobadvaisor.evals.feature_extraction import normalize
from jobadvaisor.index import state_path
from jobadvaisor.llm import Decider, decider_client, model_client
from jobadvaisor.settings import REPOSITORY_ROOT, Settings
from jobadvaisor.tools.extraction import (
    FACTS_RULE,
    INSTRUCTIONS,
    extract_features,
    feature_set,
)


class BenchmarkError(Exception):
    """A request the benchmark cannot serve; the message says why, for the user."""


class StateDirectoryError(BenchmarkError):
    """The state directory lies where private benchmark output must not go; the message names
    the `STATE_DIRECTORY` setting."""


def check_state_directory(state_directory: Path, data_root: Path) -> None:
    """Raise `StateDirectoryError` when `state_directory` lies inside this repository or inside
    the data repository at `data_root`, symlinks and `..` resolved. The records, extracted values
    and disagreements hold data from real postings and belong in neither git history. Call it
    before any model call."""
    resolved = state_directory.resolve()
    for root, name in ((REPOSITORY_ROOT, "this repository"), (data_root, "the data repository")):
        if resolved.is_relative_to(root.resolve()):
            raise StateDirectoryError(f"STATE_DIRECTORY ({state_directory}) lies inside {name}; "
                                      f"set it to a directory outside both repositories")


@dataclass(frozen=True)
class Call:
    """One extraction call. `values` is feature ID → extracted value, `None` when the call failed
    and then `error` holds its message and `error_type` the exception's class name. `cost` (US
    dollars) and `uncosted` (calls without a reported cost) come from the router's usage data;
    `latency_s` is the wall-clock time."""

    posting: str
    values: dict | None
    error: str | None
    error_type: str | None
    cost: float
    uncosted: int
    latency_s: float


def extract_choices_without_facts(posting: Posting, features: list[Feature],
                                  decider: Decider, facts: Company | None = None) -> dict:
    """`extract_choices`, given the company facts it has no question for and so ignores."""
    return extract_choices(posting, features, decider)


def extract_postings(repository: DataRepository, model: BaseChatModel | Decider,
                     features: list[Feature], limit: int | None = None,
                     only: Collection[str] | None = None,
                     extract: Callable = extract_features) -> list[Call]:
    """Extract the first `limit` postings (all when `None`) in posting-ID order, one sequential
    call each, so the latency is the time of one call; `only` restricts them to those IDs.
    `extract(posting, features, model, facts)` returns feature ID → value, `facts` being the
    posting company's record or `None`: the extractor's structured output by default,
    `extract_choices_without_facts` for a decision model. A failing call becomes a `Call` with
    `error` set and never stops the run."""
    calls = []
    for posting_id in sorted(repository.postings.keys() & set(only) if only is not None
                             else repository.postings)[:limit]:
        values = error = error_type = None
        started = time.perf_counter()
        with metered() as meter:
            try:
                posting = repository.postings[posting_id]
                values = extract(posting, features, model, repository.company_of(posting))
            except Exception as failure:  # one bad answer must not end the run
                error, error_type = str(failure), type(failure).__name__
        calls.append(Call(posting_id, values, error, error_type, meter.cost, meter.uncosted,
                          time.perf_counter() - started))
    return calls


def langfuse_client(settings: Settings) -> Langfuse | None:
    """A Langfuse client for the configured instance, or `None` unless both keys are set."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    return Langfuse(public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key, base_url=settings.langfuse_base_url)


def run(repository: DataRepository, settings: Settings, deepeval: DeepEval, *, model: str,
        base_url: str | None, chat: BaseChatModel | Decider, role: str = "extractor",
        limit: int | None = None, now: datetime | None = None, langfuse: Langfuse | None = None
        ) -> tuple[dict, dict[str, str]]:
    """Run the extractor `chat` (named `model`, reached at `base_url`) over the postings, store the
    run and return `(record, errors)`. With `role` `"decider"`, `chat` is a `Decider` answering the
    categorical features as choice questions; accuracy then counts only the labelled features it
    answered.

    The record is the JSONL line appended to `<state>/benchmark/records.jsonl`: figures, the
    approach parameters and each error's type, never posting text or extracted values. Those go
    to `<state>/benchmark/runs/<run id>.json` with the full error messages, which `errors` (posting
    ID → message) also returns for the table. Raises `FileExistsError`, before any model call,
    when a run of the same second and model is already stored. `deepeval` must be loaded for the
    state directory (see `load_deepeval`). With a `langfuse` client the run is then mirrored there
    as an experiment; a failure of that only prints a warning to stderr.
    """
    state = state_path(settings, repository.root)
    started = now or datetime.now(UTC)
    run_id = f"{started:%Y%m%dT%H%M%SZ}-{re.sub(r'[^A-Za-z0-9._-]', '_', model)}"
    values_file = state / "benchmark" / "runs" / f"{run_id}.json"
    if values_file.exists():
        raise FileExistsError(f"run {run_id} is already stored in {values_file}")
    features = feature_set(repository.policy_pack.feature_set)
    decision = role == "decider"
    calls = extract_postings(repository, chat, features, limit,
                             extract=extract_choices_without_facts if decision
                             else extract_features)
    approach = approach_parameters(features, **(
        {"instructions": json.dumps(_questions(features), sort_keys=True)} if decision else {}))
    labels = repository.extraction_labels.labels if repository.extraction_labels else {}
    answered = {feature.id for feature in features if feature.type == "categorical"}
    scored = ({posting: {feature: value for feature, value in wanted.items() if feature in answered}
               for posting, wanted in labels.items()} if decision else labels)
    per_feature = score_accuracy(
        deepeval, {call.posting: call.values for call in calls}, scored, run_id,
        {"model": model, "base_url": base_url or "",
         "instructions_hash": approach["instructions_hash"],
         "feature_set_hash": approach["feature_set_hash"]})
    errors = {call.posting: call.error for call in calls if call.error is not None}
    record = {
        "run_id": run_id, "date": started.isoformat(), "data": state.name, "role": role,
        "model": model, "base_url": base_url, **approach, "postings": len(calls),
        "metrics": _metrics(per_feature),
        "cost_per_posting_usd": sum(call.cost for call in calls) / len(calls) if calls else None,
        "uncosted_calls": sum(call.uncosted for call in calls),
        "mean_latency_s": mean(call.latency_s for call in calls) if calls else None,
        "errors": [{"posting": call.posting, "error_type": call.error_type}
                   for call in calls if call.error is not None]}
    values_file.parent.mkdir(parents=True, exist_ok=True)
    values_file.write_text(json.dumps(
        {"run_id": run_id, "values": {call.posting: call.values for call in calls
                                      if call.values is not None}, "errors": errors},
        indent=2, ensure_ascii=False) + "\n")
    with (state / "benchmark" / "records.jsonl").open("a") as records:
        records.write(json.dumps(record, ensure_ascii=False) + "\n")
    if langfuse is not None:
        try:
            _mirror(langfuse, record, {call.posting: call.values for call in calls}, errors,
                    labels)
        except Exception as failure:  # the mirror is a convenience; the record is the history
            print(f"warning: Langfuse mirror failed: {failure}", file=sys.stderr)
    return record, errors


def _mirror(client: Langfuse, record: dict, extracted: dict[str, dict | None],
            errors: dict[str, str], labels: dict[str, dict]) -> None:
    """Record the run in Langfuse as an experiment named `extractor-benchmark` whose run is the
    run ID: one item per posting (input the posting ID, expected output its labels), the stored
    values replayed as the task's output (a failed call as its error) so nothing is paid twice,
    and run-level scores for the accuracy (per feature and pooled, with the case count), cost per
    posting and mean latency."""
    scores = []
    for metric in record["metrics"]:
        scores += [Evaluation(name=f"accuracy/{feature}", value=figures["value"],
                              comment=f"{metric['name']}, {figures['cases']} cases",
                              metadata={"cases": figures["cases"]})
                   for feature, figures in metric["per_feature"].items()]
        scores.append(Evaluation(name="accuracy", value=metric["value"],
                                 comment=f"{metric['name']}, {metric['cases']} cases",
                                 metadata={"cases": metric["cases"]}))
    for name, value in (("cost_per_posting_usd", record["cost_per_posting_usd"]),
                        ("latency_mean_s", record["mean_latency_s"])):
        if value is not None:
            scores.append(Evaluation(name=name, value=value))
    parameters = ("role", "model", "base_url", "instructions_hash", "feature_set_hash", "commit")
    client.run_experiment(
        name="extractor-benchmark", run_name=record["run_id"],
        data=[{"input": posting, "expected_output": labels.get(posting) or None}
              for posting in extracted],
        task=lambda *, item, **_: (extracted[item["input"]] if extracted[item["input"]] is not None
                                   else {"error": errors[item["input"]]}),
        run_evaluators=[lambda **_: scores], max_concurrency=1,
        metadata={name: str(record[name]) for name in parameters if record[name] is not None})
    client.flush()


def _questions(features: list[Feature]) -> dict[str, dict]:
    """The choice questions a decision model is asked: one per categorical feature."""
    return {feature.id: choice_question(feature)
            for feature in features if feature.type == "categorical"}


def _metrics(per_feature: dict[str, dict]) -> list[dict]:
    """The record's metric list: the accuracy pooled over all labelled feature values, with its
    case count and the per-feature figures; empty without labels."""
    if not per_feature:
        return []
    cases = sum(figures["cases"] for figures in per_feature.values())
    return [{"name": ACCURACY, "value": pooled_accuracy(per_feature), "cases": cases,
             "per_feature": {feature: {"value": figures["accuracy"], "cases": figures["cases"]}
                             for feature, figures in per_feature.items()}}]


def format_table(record: dict, errors: dict[str, str]) -> str:
    """The run as one table: the per-feature result (naming the metric and each case count), cost
    per posting, mean latency, posting count and the errors with their messages."""
    kind = " (decision model)" if record["role"] == "decider" else ""
    lines = [f"extractor benchmark{kind}: {record['model']} (run {record['run_id']})", ""]
    if record["metrics"]:
        [metric] = record["metrics"]
        lines.append(f"{metric['name']} (labelled cases only)")
        lines += [f"  {feature:<20}{figures['value']:.2f}  ({figures['cases']} cases)"
                  for feature, figures in metric["per_feature"].items()]
    else:
        lines.append("no accuracy computed: the data repository holds no extraction labels")
    lines += ["",
              f"cost per posting    {_cost(record['cost_per_posting_usd'])}"
              + (f" ({record['uncosted_calls']} calls without a reported cost)"
                 if record["uncosted_calls"] else ""),
              f"mean latency        {_seconds(record['mean_latency_s'])}",
              f"postings            {record['postings']}",
              f"errors              {len(errors)}"]
    lines += [f"  {posting}: {message}" for posting, message in errors.items()]
    return "\n".join(lines)


def read_records(state: Path) -> list[dict]:
    """The stored records under the state path `state`, oldest first; empty when none exist."""
    file = state / "benchmark" / "records.jsonl"
    return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []


def compare(state: Path, run_ids: list[str], labels: dict[str, dict]) -> dict:
    """Compare the stored runs `run_ids` of the state path `state`, over the postings every run
    answered. `labels` (posting ID → feature ID → value) are the cases already settled.

    Returns `runs` (run ID, model, cost per posting, mean latency), `postings` (how many were
    compared), `agreement` (feature ID → `value`, the share of those postings on which all runs
    gave an equal value, and `postings`) and `disagreements`: one `{posting, feature, runs: {run
    ID: value}, label: None}` per unlabelled case with differing values, the postings with the
    most differing features first. Raises `BenchmarkError` for fewer than two runs or a run that
    is not stored.
    """
    if len(run_ids) < 2:
        raise BenchmarkError("a comparison needs at least two runs; pass two or more run IDs "
                             "(--history lists them)")
    records = {record["run_id"]: record for record in read_records(state)}
    stored = {}
    for run_id in run_ids:
        file = state / "benchmark" / "runs" / f"{run_id}.json"
        if run_id not in records or not file.exists():
            raise BenchmarkError(f"no stored run {run_id} (--history lists the stored runs)")
        stored[run_id] = json.loads(file.read_text())["values"]
    common = sorted(set.intersection(*(set(values) for values in stored.values())))
    first = stored[run_ids[0]]
    features = [feature for feature in (first[common[0]] if common else [])
                if all(feature in values[posting] for values in stored.values()
                       for posting in common)]
    agreement, differing = {}, {posting: [] for posting in common}
    for feature in features:
        same = 0
        for posting in common:
            given = {run_id: values[posting][feature] for run_id, values in stored.items()}
            if len({json.dumps(normalize(value)) for value in given.values()}) == 1:
                same += 1
            elif feature not in labels.get(posting, {}):
                differing[posting].append({"posting": posting, "feature": feature,
                                           "runs": given, "label": None})
        agreement[feature] = {"value": same / len(common), "postings": len(common)}
    disagreements = [case for posting in sorted(common, key=lambda p: (-len(differing[p]), p))
                     for case in differing[posting]]
    return {"runs": [{key: records[run_id][key] for key in
                      ("run_id", "model", "cost_per_posting_usd", "mean_latency_s")}
                     for run_id in run_ids],
            "postings": len(common), "agreement": agreement, "disagreements": disagreements}


def format_comparison(result: dict) -> str:
    """The comparison as one report: the agreement per feature with its posting count, then each
    run's model, cost per posting and mean latency side by side."""
    lines = [f"comparison of {len(result['runs'])} runs, compared on {result['postings']} "
             f"postings that every run answered", "",
             "agreement (share of postings on which all runs gave the same value)"]
    lines += [f"  {feature:<20}{figures['value']:.2f}  ({figures['postings']} postings)"
              for feature, figures in result["agreement"].items()]
    lines += ["", f"{'run':<40}{'model':<28}{'cost per posting':<18}mean latency"]
    lines += [f"{run['run_id']:<40}{run['model']:<28}{_cost(run['cost_per_posting_usd']):<18}"
              f"{_seconds(run['mean_latency_s'])}" for run in result["runs"]]
    lines += ["", f"{len(result['disagreements'])} unlabelled disagreements"]
    return "\n".join(lines)


def write_disagreements(state: Path, disagreements: list[dict], now: datetime) -> Path | None:
    """Write `disagreements` (from `compare`) to `<state>/benchmark/disagreements-<stamp>.json`
    for the user to fill in `label`, and return the path; `None` (nothing written) when there are
    none. Raises `FileExistsError` rather than overwrite a file of the same second."""
    if not disagreements:
        return None
    path = state / "benchmark" / f"disagreements-{now:%Y%m%dT%H%M%SZ}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as file:
        file.write(json.dumps(disagreements, indent=2, ensure_ascii=False) + "\n")
    return path


def settle(data_root: Path, file: Path) -> int:
    """Merge the filled entries of the disagreements `file` into the extraction labels of the data
    repository at `data_root` and return how many were merged. An entry whose `label` is `null` or
    empty stays out; a filled one replaces an existing label. Raises `BenchmarkError` for an
    unreadable file or a label the repository rejects; the labels file is then unchanged."""
    try:
        entries = json.loads(file.read_text())
        additions: dict[str, dict] = {}
        for entry in entries:
            if entry["label"] not in (None, ""):
                additions.setdefault(entry["posting"], {})[entry["feature"]] = entry["label"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise BenchmarkError(f"{file} is not a disagreements file: {error}") from None
    if not additions:
        return 0
    try:
        merge_extraction_labels(data_root, additions)
    except (DataRepositoryError, ValueError) as error:
        raise BenchmarkError(f"the labels were not merged: {error}") from None
    return sum(len(values) for values in additions.values())


def format_history(records: list[dict]) -> str:
    """The stored records as a table, one row per run: date, model, metric with its value and
    case count, cost per posting, mean latency, posting count and the run ID `--compare` takes."""
    lines = [f"{'date':<18}{'model':<28}{'metric':<34}{'cases':<7}{'cost':<10}{'latency':<10}"
             f"{'postings':<10}run"]
    for record in records:
        [metric, *_] = record["metrics"] or [None]
        shown = f"{metric['name']} {metric['value']:.2f}" if metric else "-"
        lines.append(f"{record['date'][:16].replace('T', ' '):<18}{record['model']:<28}"
                     f"{shown:<34}{metric['cases'] if metric else '-':<7}"
                     f"{_cost(record['cost_per_posting_usd']):<10}"
                     f"{_seconds(record['mean_latency_s']):<10}{record['postings']:<10}"
                     f"{record['run_id']}")
    return "\n".join(lines)


def _cost(cost: float | None) -> str:
    return "n/a" if cost is None else f"${cost:.4f}"


def _seconds(seconds: float | None) -> str:
    return "n/a" if seconds is None else f"{seconds:.2f} s"


def approach_parameters(features: list[Feature],
                        instructions: str = f"{INSTRUCTIONS}\n\n{FACTS_RULE}",
                        root: Path = REPOSITORY_ROOT) -> dict:
    """The parameters that define the extraction approach besides the model: a hash of the
    `instructions` (by default the extractor's, with its company-facts rule), a hash of the
    extracted `features`, and the app's git `commit` (`None` when `root` is no git checkout), so
    a change of approach shows in the stored records."""
    feature_text = json.dumps([feature.model_dump() for feature in features], sort_keys=True)
    return {"instructions_hash": _hash(instructions), "feature_set_hash": _hash(feature_text),
            "commit": _commit(root)}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _commit(root: Path) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None


def main(argv: list[str] | None = None) -> None:
    """`python -m jobadvaisor.evals.extractor_benchmark [--data PATH] [--role extractor|decider]
    [--model M] [--base-url U] [--limit N] [--compare RUN_ID ...] [--settle FILE] [--history]`

    Without a mode flag, runs the extractor over the postings of `--data` (default: the demo
    persona) and prints the table. The model is `EXTRACTOR_MODEL` (falling back to `LLM_MODEL`)
    unless `--model` names another; its base URL is `--base-url`, else the configured extractor
    base URL. `--role decider` runs the hosted decision model instead (`DECIDER_MODEL` and
    `DECIDER_BASE_URL`, falling back to `LLM_BASE_URL`), which answers the categorical features
    only. `--compare` reports two or more stored runs side by side and writes their
    unlabelled disagreements to a file; `--settle` merges that file, once filled in, into the
    data repository's extraction labels; `--history` lists the stored runs. Every mode stops with
    a usage error, before any model call, when the state directory lies inside this repository or
    the data repository.
    """
    parser = argparse.ArgumentParser(prog="python -m jobadvaisor.evals.extractor_benchmark")
    parser.add_argument("--data", type=Path, default=FIXTURE_DIRECTORY)
    parser.add_argument("--role", choices=("extractor", "decider"), default="extractor",
                        help="what the run evaluates: the extractor or the decision model")
    parser.add_argument("--model", help="model for this run instead of the configured one")
    parser.add_argument("--base-url", help="base URL for this run instead of the configured one")
    parser.add_argument("--limit", type=int, help="extract only the first N postings in ID order")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--compare", nargs="+", metavar="RUN_ID",
                       help="compare two or more stored runs")
    modes.add_argument("--settle", type=Path, metavar="FILE",
                       help="merge a filled-in disagreements file into the extraction labels")
    modes.add_argument("--history", action="store_true", help="list the stored runs")
    args = parser.parse_args(argv)
    settings = Settings()
    try:
        check_state_directory(settings.state_directory, args.data)
        state = state_path(settings, args.data)
        if args.history:
            print(format_history(read_records(state)))
        elif args.compare:
            _compare_command(args.data, state, args.compare)
        elif args.settle:
            print(f"merged {settle(args.data, args.settle)} label(s) into "
                  f"{args.data / 'extraction-labels.json'}")
        else:
            _run_command(settings, args)
    except BenchmarkError as error:
        parser.error(str(error))


def _run_command(settings: Settings, args: argparse.Namespace) -> None:
    """The run mode of `main`: build the model for `args`, run, print the table."""
    decision = args.role == "decider"
    model = args.model or (settings.decider_model if decision
                           else settings.extractor_model or settings.llm_model)
    if not model:
        raise BenchmarkError("DECIDER_MODEL is not set" if decision
                             else "EXTRACTOR_MODEL or LLM_MODEL is not set")
    base_url = args.base_url or (settings.decider_base_url if decision
                                 else settings.extractor_base_url) or settings.llm_base_url
    repository = load(args.data)
    deepeval = load_deepeval(state_path(settings, repository.root))
    chat = (decider_client if decision else model_client)(model, base_url, settings)
    record, errors = run(repository, settings, deepeval, model=model, base_url=base_url,
                         chat=chat, role=args.role, limit=args.limit,
                         langfuse=langfuse_client(settings))
    print(format_table(record, errors))


def _compare_command(data: Path, state: Path, run_ids: list[str]) -> None:
    """The compare mode of `main`: print the comparison and write the disagreements file."""
    extraction_labels = load(data).extraction_labels
    result = compare(state, run_ids, extraction_labels.labels if extraction_labels else {})
    print(format_comparison(result))
    path = write_disagreements(state, result["disagreements"], datetime.now(UTC))
    if path:
        print(f"disagreements file: {path}\n"
              f"fill in \"label\" for the cases you can judge, then run --settle {path}")


if __name__ == "__main__":
    main()
