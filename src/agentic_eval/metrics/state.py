"""Outcome metrics: did the conversation leave the world in the expected state?"""

from __future__ import annotations

import re

from agentic_eval.core.matching import match_mapping
from agentic_eval.core.registry import register_metric
from agentic_eval.core.results import MetricResult
from agentic_eval.core.testcase import TestCase
from agentic_eval.core.trace import Capability, Trace
from agentic_eval.interfaces.metric import Metric, MetricContext
from agentic_eval.metrics._common import safe_resolve


@register_metric("final_state")
class FinalStateMetric(Metric):
    """Expected keys in the final state (literals, refs or matchers)."""

    name = "final_state"
    expectation_key = "final_state"
    requires = frozenset({Capability.STATE})

    def evaluate(self, trace: Trace, case: TestCase, ctx: MetricContext) -> MetricResult:
        expected, err = safe_resolve(case.expectations.final_state, trace, case, None)
        if err:
            return MetricResult.from_score(self.name, 0.0, self.threshold, err)
        actual = trace.final_state
        ok, frac, mismatches = match_mapping(expected, actual)
        return MetricResult.from_score(
            self.name, frac, self.threshold,
            "final state matches" if ok else f"mismatches: {mismatches}",
            {"expected": expected, "actual": actual, "mismatches": mismatches},
        )


@register_metric("final_response")
class FinalResponseMetric(Metric):
    """Checks on the last turn's response text.

    Keys: ``contains`` (str or list), ``not_contains`` (str or list),
    ``regex``, ``case_sensitive`` (default false).
    """

    name = "final_response"
    expectation_key = "final_response"
    requires = frozenset({Capability.MESSAGES})

    def evaluate(self, trace: Trace, case: TestCase, ctx: MetricContext) -> MetricResult:
        spec, err = safe_resolve(case.expectations.final_response, trace, case, None)
        if err:
            return MetricResult.from_score(self.name, 0.0, self.threshold, err)
        text = trace.turns[-1].response_text if trace.turns else ""
        cs = bool(spec.get("case_sensitive", False))
        norm = (lambda s: s) if cs else (lambda s: s.casefold())
        checks, failures = 0, []

        def as_list(v):
            return v if isinstance(v, list) else [v]

        for needle in as_list(spec.get("contains", [])):
            checks += 1
            if norm(str(needle)) not in norm(text):
                failures.append(f"missing {needle!r}")
        for needle in as_list(spec.get("not_contains", [])):
            checks += 1
            if norm(str(needle)) in norm(text):
                failures.append(f"should not contain {needle!r}")
        if spec.get("regex"):
            checks += 1
            if not re.search(spec["regex"], text, 0 if cs else re.IGNORECASE):
                failures.append(f"regex {spec['regex']!r} not found")
        score = (checks - len(failures)) / checks if checks else 1.0
        return MetricResult.from_score(
            self.name, score, self.threshold,
            "; ".join(failures) or "response checks passed",
            {"response": text[:2000], "failures": failures},
        )
