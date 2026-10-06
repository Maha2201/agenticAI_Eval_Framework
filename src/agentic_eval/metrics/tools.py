"""Tool-use metrics."""

from __future__ import annotations

from agentic_eval.core.matching import match_mapping
from agentic_eval.core.registry import register_metric
from agentic_eval.core.results import MetricResult
from agentic_eval.core.testcase import ExpectedToolCall, TestCase
from agentic_eval.core.trace import Capability, Trace
from agentic_eval.interfaces.metric import Metric, MetricContext
from agentic_eval.metrics._common import safe_resolve


def _calls_for(trace: Trace, exp: ExpectedToolCall):
    out = []
    for call in trace.tool_calls:
        if call.tool != exp.tool:
            continue
        if exp.turn is not None and trace.turn_of(call.id) != exp.turn:
            continue
        out.append(call)
    return out


@register_metric("tool_selection")
class ToolSelectionMetric(Metric):
    """Were the expected tools called (right number of times, optionally in order)?

    Score = satisfied expectations / (expected + unexpected calls when
    ``allow_unexpected`` is false). ``expected: []`` with
    ``allow_unexpected: false`` asserts that no tool is called at all.
    """

    name = "tool_selection"
    expectation_key = "tool_calls"
    requires = frozenset({Capability.TOOL_CALLS})

    def applies_to(self, case: TestCase) -> bool:
        tc = case.expectations.tool_calls
        return tc is not None and (bool(tc.expected) or not tc.allow_unexpected)

    def evaluate(self, trace: Trace, case: TestCase, ctx: MetricContext) -> MetricResult:
        tc = case.expectations.tool_calls
        assert tc is not None
        called = [c.tool for c in trace.tool_calls]
        satisfied, notes = 0, []
        first_positions: list[int] = []
        for exp in tc.expected:
            calls = _calls_for(trace, exp)
            n = len(calls)
            ok = n >= exp.min_calls and (exp.max_calls is None or n <= exp.max_calls)
            if ok:
                satisfied += 1
            else:
                bound = f"{exp.min_calls}..{exp.max_calls if exp.max_calls is not None else 'n'}"
                where = f" in turn {exp.turn}" if exp.turn is not None else ""
                notes.append(f"{exp.tool}{where}: called {n}x, expected {bound}")
            if calls:
                first_positions.append(trace.tool_calls.index(calls[0]))
        order_ok = True
        if tc.ordered and len(first_positions) == len(tc.expected):
            order_ok = first_positions == sorted(first_positions)
            if not order_ok:
                notes.append("expected tools called out of order")
        expected_names = {e.tool for e in tc.expected}
        unexpected = [] if tc.allow_unexpected else [t for t in called if t not in expected_names]
        if unexpected:
            notes.append(f"unexpected tool calls: {unexpected}")
        denom = len(tc.expected) + len(unexpected)
        score = (satisfied / denom) if denom else 1.0
        if not order_ok:
            score = 0.0
        return MetricResult.from_score(
            self.name, score, self.threshold,
            "; ".join(notes) or f"all expected tools called ({sorted(expected_names) or 'none'})",
            {"called": called, "expected": [e.tool for e in tc.expected],
             "unexpected": unexpected},
        )


@register_metric("tool_arguments")
class ToolArgumentsMetric(Metric):
    """Were the expected tools called with the right arguments?

    Expected values may be literals, ``{{ state.x }}`` references (resolved
    against the state after the turn of the call) or matchers. For each
    expected call, the best-matching actual call is scored by the fraction of
    arguments that match; the metric is the mean across expected calls.
    """

    name = "tool_arguments"
    expectation_key = "tool_calls"
    requires = frozenset({Capability.TOOL_CALLS, Capability.TOOL_ARGUMENTS})

    def applies_to(self, case: TestCase) -> bool:
        tc = case.expectations.tool_calls
        return tc is not None and any(e.arguments for e in tc.expected)

    def evaluate(self, trace: Trace, case: TestCase, ctx: MetricContext) -> MetricResult:
        tc = case.expectations.tool_calls
        assert tc is not None
        scores, per_call = [], []
        for exp in (e for e in tc.expected if e.arguments):
            best, best_detail = 0.0, {"tool": exp.tool, "result": "not called"}
            for call in _calls_for(trace, exp):
                expected_args, err = safe_resolve(exp.arguments, trace, case, trace.turn_of(call.id))
                if err:
                    detail = {"tool": exp.tool, "result": err}
                    if best == 0.0:
                        best_detail = detail
                    continue
                ok, frac, mismatches = match_mapping(
                    expected_args, call.arguments, exact=exp.arguments_match == "exact"
                )
                if frac >= best:
                    best = frac
                    best_detail = {"tool": exp.tool, "expected": expected_args,
                                   "actual": call.arguments, "mismatches": mismatches,
                                   "result": "match" if ok else "mismatch"}
            scores.append(best)
            per_call.append(best_detail)
        score = sum(scores) / len(scores) if scores else 1.0
        bad = [d for d in per_call if d.get("result") != "match"]
        reason = ("all arguments matched" if not bad else
                  "; ".join(f"{d['tool']}: {d.get('mismatches') or d['result']}" for d in bad))
        return MetricResult.from_score(self.name, score, self.threshold, reason, {"calls": per_call})


@register_metric("forbidden_tools")
class ForbiddenToolsMetric(Metric):
    """No call to a tool listed in ``tool_calls.forbidden``."""

    name = "forbidden_tools"
    expectation_key = "tool_calls"
    requires = frozenset({Capability.TOOL_CALLS})

    def applies_to(self, case: TestCase) -> bool:
        tc = case.expectations.tool_calls
        return tc is not None and bool(tc.forbidden)

    def evaluate(self, trace: Trace, case: TestCase, ctx: MetricContext) -> MetricResult:
        tc = case.expectations.tool_calls
        assert tc is not None
        hits = [c.tool for c in trace.tool_calls if c.tool in tc.forbidden]
        return MetricResult.from_score(
            self.name, 0.0 if hits else 1.0, self.threshold,
            f"forbidden tools called: {hits}" if hits else "no forbidden tools called",
            {"forbidden_called": hits},
        )


@register_metric("tool_scope")
class ToolScopeMetric(Metric):
    """Every tool call and handoff stays within the calling agent's permissions.

    Needs the agent manifest (which tools and handoffs each agent is allowed).
    Runs as a default metric: it needs no per-case expectation.
    """

    name = "tool_scope"
    requires = frozenset({Capability.AGENT_MANIFEST, Capability.TOOL_CALLS})

    def evaluate(self, trace: Trace, case: TestCase, ctx: MetricContext) -> MetricResult:
        checks, violations = 0, []
        for call in trace.tool_calls:
            spec = trace.agents.get(call.agent or "")
            if spec is None:
                continue
            checks += 1
            if call.tool not in spec.tools:
                violations.append(f"{call.agent} called {call.tool} (allowed: {spec.tools})")
        for h in trace.handoffs:
            spec = trace.agents.get(h.source or "")
            if spec is None or h.target is None:
                continue
            checks += 1
            if h.target not in spec.handoffs:
                violations.append(f"{h.source} handed off to {h.target} (allowed: {spec.handoffs})")
        score = 1.0 - len(violations) / checks if checks else 1.0
        return MetricResult.from_score(
            self.name, score, self.threshold,
            "; ".join(violations) or f"{checks} actions within scope",
            {"checks": checks, "violations": violations},
        )
