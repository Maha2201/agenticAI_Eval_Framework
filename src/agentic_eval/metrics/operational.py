"""Operational metrics."""

from __future__ import annotations

from agentic_eval.core.registry import register_metric
from agentic_eval.core.results import MetricResult
from agentic_eval.core.testcase import TestCase
from agentic_eval.core.trace import Trace
from agentic_eval.interfaces.metric import Metric, MetricContext


@register_metric("latency")
class LatencyMetric(Metric):
    """Per-turn and total latency, measured by the framework around each call."""

    name = "latency"
    expectation_key = "latency"

    def evaluate(self, trace: Trace, case: TestCase, ctx: MetricContext) -> MetricResult:
        exp = case.expectations.latency
        assert exp is not None
        lat = [t.latency_ms for t in trace.turns if t.latency_ms is not None]
        if not lat:
            return MetricResult.not_applicable(self.name, "no latency measured")
        worst, total = max(lat), sum(lat)
        failures = []
        if exp.max_turn_ms is not None and worst > exp.max_turn_ms:
            failures.append(f"slowest turn {worst:.0f} ms > {exp.max_turn_ms:.0f} ms")
        if exp.max_total_ms is not None and total > exp.max_total_ms:
            failures.append(f"total {total:.0f} ms > {exp.max_total_ms:.0f} ms")
        return MetricResult.from_score(
            self.name, 0.0 if failures else 1.0, self.threshold,
            "; ".join(failures) or f"slowest turn {worst:.0f} ms, total {total:.0f} ms",
            {"turn_latency_ms": [round(x, 1) for x in lat], "total_ms": round(total, 1)},
        )
