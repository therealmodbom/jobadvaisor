"""DeepEval runs offline and keeps every file it writes in the state directory.

DeepEval reads its cache folder when first imported, so each case runs in a fresh interpreter.
"""

import subprocess
import sys

EXACT_METRIC_RUN = '''
import socket, sys
from pathlib import Path

attempts = []

def refuse(*args, **kwargs):
    attempts.append(args)
    raise OSError("network is off in this test")

socket.socket.connect = refuse
socket.getaddrinfo = refuse

from jobadvaisor.evals.deepeval_runtime import load_deepeval

deepeval = load_deepeval(Path(sys.argv[1]))


class Exact(deepeval.BaseMetric):
    def __init__(self):
        self.threshold = 1.0
        self.async_mode = False
        self.evaluation_model = None
        self.strict_mode = False
        self.verbose_mode = False

    def measure(self, test_case, *args, **kwargs):
        self.score = float(test_case.actual_output == test_case.expected_output)
        self.reason = "equal" if self.score else "differs"
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case, *args, **kwargs):
        return self.measure(test_case)

    def is_successful(self):
        return self.success

    @property
    def __name__(self):
        return "Exact"


result = deepeval.evaluate(
    [deepeval.LLMTestCase(input="p1", actual_output="a", expected_output="a")], [Exact()],
    identifier="run-1", hyperparameters={"model": "m"})
data = result.test_results[0].metrics_data[0]
print(data.score, data.reason, len(attempts))
'''

IMPORTED_ELSEWHERE_FIRST = '''
import sys
from pathlib import Path

import deepeval
from jobadvaisor.evals.deepeval_runtime import load_deepeval

try:
    load_deepeval(Path(sys.argv[1]))
except RuntimeError as error:
    print("refused", error)
'''


def run_python(script, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    return work, subprocess.run([sys.executable, "-c", script, str(tmp_path / "state")], cwd=work,
                                capture_output=True, text=True, timeout=120)


def test_custom_metric_runs_offline_and_writes_only_into_the_state_directory(tmp_path):
    work, process = run_python(EXACT_METRIC_RUN, tmp_path)
    assert process.returncode == 0, process.stderr
    assert process.stdout.splitlines()[-1] == "1.0 equal 0"
    assert list(work.iterdir()) == []
    assert any(path.is_file() for path in (tmp_path / "state").rglob("*"))


def test_deepeval_imported_before_the_helper_is_refused(tmp_path):
    _, process = run_python(IMPORTED_ELSEWHERE_FIRST, tmp_path)
    assert process.returncode == 0, process.stderr
    assert process.stdout.startswith("refused ")
