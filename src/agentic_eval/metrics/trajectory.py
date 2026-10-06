"""Trajectory metrics: which agents handled the conversation, in what order."""

from __future__ import annotations

from agentic_eval.core.registry import register_metric
from agentic_eval.core.results import MetricResult
from agentic_eval.core.testcase import PathMode, TestCase
from agentic_eval.core.trace import Capability, Trace
from agentic_eval.interfaces.metric import Metric, MetricContext


def is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    it = iter(haystack)
    return all(any(x == y for y in it) for x in needle)


@register_metric("agent_path")
class AgentPathMetric(Metric):
    """Did control move through the expected agents?

    Modes: exact, prefix, subsequence (default; gaps allowed, order kept),
    contains (any order). ``forbidden`` agents must never take control, which
    also covers "this should have stayed with the entry agent".
    """

    name = "agent_path"
    expectation_key = "agent_path"
    requires = frozenset({Capability.HANDOFFS})

    def evaluate(self, trace: Trace, case: TestCase, ctx: MetricContext) -> MetricResult:
        exp = case.expectations.agent_path
        assert exp is not None
        path = trace.agent_path()
        seq = exp.sequence
        if exp.mode == PathMode.EXACT:
            ok = path == seq
        elif exp.mode == PathMode.PREFIX:
            ok = path[: len(seq)] == seq
        elif exp.mode == PathMode.CONTAINS:
            ok = all(a in path for a in seq)
        else:
            ok = is_subsequence(seq, path)
        hit_forbidden = [a for a in exp.forbidden if a in path]
        passed = ok and not hit_forbidden
        parts = [f"path {path} {'matches' if ok else 'does not match'} {seq} ({exp.mode.value})"]
        if hit_forbidden:
            parts.append(f"forbidden agents took control: {hit_forbidden}")
        return MetricResult.from_score(
            self.name,
            1.0 if passed else 0.0,
            self.threshold,
            "; ".join(parts),
            {"actual_path": path, "expected": seq, "mode": exp.mode.value,
             "forbidden_hit": hit_forbidden},
        )
