"""The only place that imports `deepeval` (benchmark `design.md` → DeepEval).

DeepEval writes full test cases (input, actual and expected output) to a `.deepeval/` folder in the
working directory and reads that location once, at import. This module points the folder into the
state directory before the first import and switches DeepEval's telemetry off.
"""

import contextlib
import io
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DeepEval:
    """The DeepEval pieces the benchmark uses: `evaluate`, the `BaseMetric` class to subclass and
    the `LLMTestCase` to score."""

    evaluate: object
    BaseMetric: type
    LLMTestCase: type


def load_deepeval(state_directory: Path) -> DeepEval:
    """Import DeepEval with its files kept under `state_directory/deepeval` (an already checked
    state directory, outside both repositories) and return what the benchmark uses.

    Raises `RuntimeError` when DeepEval was imported earlier in this process, since it has then
    fixed its folder (normally `.deepeval` in the working directory) and cannot be moved.
    """
    folder = state_directory / "deepeval"
    (folder / "results").mkdir(parents=True, exist_ok=True)
    os.environ["DEEPEVAL_CACHE_FOLDER"] = str(folder)
    os.environ["DEEPEVAL_RESULTS_FOLDER"] = str(folder / "results")
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

    from deepeval import evaluate
    from deepeval.constants import HIDDEN_DIR
    from deepeval.evaluate.configs import AsyncConfig, DisplayConfig
    from deepeval.metrics import BaseMetric
    from deepeval.test_case import LLMTestCase

    if HIDDEN_DIR != str(folder):
        raise RuntimeError(f"DeepEval was imported before its folder was set (it uses "
                           f"{HIDDEN_DIR}, not {folder}); import it only through load_deepeval, "
                           f"or export DEEPEVAL_CACHE_FOLDER={folder} before starting the process")

    def quiet_evaluate(*args, **kwargs):
        """`evaluate` without DeepEval's terminal output (its report prints each case's actual and
        expected output, and it announces where it saved the run), and sequential, so cases run
        in order."""
        with contextlib.redirect_stdout(io.StringIO()):
            return evaluate(*args, **kwargs, async_config=AsyncConfig(run_async=False),
                            display_config=DisplayConfig(show_indicator=False, print_results=False,
                                                         inspect_after_run=False))

    return DeepEval(quiet_evaluate, BaseMetric, LLMTestCase)
