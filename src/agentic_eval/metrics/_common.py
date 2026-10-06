"""Helpers shared by built-in metrics."""

from __future__ import annotations

from typing import Any

from agentic_eval.core.matching import ResolutionContext, UnresolvedReference, resolve
from agentic_eval.core.testcase import TestCase
from agentic_eval.core.trace import Trace


def resolve_for_turn(value: Any, trace: Trace, case: TestCase, turn_index: int | None) -> Any:
    """Resolve {{ refs }} against the state after the given turn (or the final state)."""
    state = trace.state_after_turn(turn_index) if turn_index is not None else trace.final_state
    return resolve(value, ResolutionContext(state=state, vars=case.vars))


def safe_resolve(
    value: Any, trace: Trace, case: TestCase, turn_index: int | None
) -> tuple[Any, str | None]:
    try:
        return resolve_for_turn(value, trace, case, turn_index), None
    except UnresolvedReference as exc:
        return None, f"unresolved reference {exc.args[0]}"


def missing_capabilities(metric: Any, trace: Trace) -> list[str]:
    return sorted(c.value for c in metric.requires if c not in trace.capabilities)
