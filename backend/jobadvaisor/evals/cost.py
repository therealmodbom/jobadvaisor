"""Metering for evals: the cost the router reports per model call, and every tool's output.

Requesty answers each call with `usage.cost` in US dollars, which LangChain keeps in the message's
`response_metadata["token_usage"]`. A call without it counts as `uncosted`, so a report can say
when its cost figure is incomplete.
"""

import threading
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.tracers.context import register_configure_hook

_ACTIVE: ContextVar["Meter | None"] = ContextVar("jobadvaisor_meter", default=None)
register_configure_hook(_ACTIVE, inheritable=True)


class Meter(BaseCallbackHandler):
    """Sums `cost` (US dollars) and counts `calls` and `uncosted` calls of every chat model
    invoked while it is active, and keeps each tool's outputs by tool name."""

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self.cost, self.calls, self.uncosted = 0.0, 0, 0
        self.tool_outputs: dict[str, list[str]] = defaultdict(list)

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Add the call's reported cost."""
        message = getattr(response.generations[0][0], "message", None) if response.generations \
            else None
        usage = getattr(message, "response_metadata", {}).get("token_usage") or {}
        self.record(usage.get("cost"))

    def record(self, cost: float | None) -> None:
        """Count one model call that reported `cost` (`None`: no cost reported)."""
        with self._lock:
            self.calls += 1
            if cost is None:
                self.uncosted += 1
            else:
                self.cost += cost

    def on_tool_end(self, output, **kwargs) -> None:
        """Keep the tool's output text under its name."""
        with self._lock:
            self.tool_outputs[kwargs.get("name") or "?"].append(
                str(getattr(output, "content", output)))


def record_call(cost: float | None) -> None:
    """Report a model call made outside LangChain (a decision-model call) with its reported `cost`
    to the active meter; does nothing without one."""
    if (meter := _ACTIVE.get()) is not None:
        meter.record(cost)


@contextmanager
def metered() -> Iterator[Meter]:
    """A `Meter` attached to every LangChain model and tool call inside the block, nested calls
    included."""
    meter = Meter()
    token = _ACTIVE.set(meter)
    try:
        yield meter
    finally:
        _ACTIVE.reset(token)
