"""DeepEval-backed metrics.

DeepEval is used here behind the framework's Metric interface: the trace is
converted to DeepEval's test case types at the last moment, so nothing else in
the framework depends on DeepEval's models. Requires ``pip install .[deepeval]``.

Verified against deepeval 4.2.8.
"""

from __future__ import annotations

import os
from typing import Any

from agentic_eval.core.matching import contains_matcher
from agentic_eval.core.registry import register_metric
from agentic_eval.core.results import MetricResult
from agentic_eval.core.testcase import TestCase
from agentic_eval.core.trace import Capability, ToolResultEvent, Trace
from agentic_eval.interfaces.metric import Metric, MetricContext
from agentic_eval.metrics._common import safe_resolve

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")


def _offline_model() -> Any:
    """A model stub that makes deterministic DeepEval metrics run with no API key.

    ToolCorrectnessMetric builds an LLM client in its constructor even when it
    only does deterministic matching (no ``available_tools``). This stub
    satisfies the constructor and raises if anything actually tries to call it.
    """
    from deepeval.models import DeepEvalBaseLLM

    class _NoLLM(DeepEvalBaseLLM):
        def __init__(self) -> None:
            super().__init__("offline-no-llm")

        def load_model(self) -> None:
            return None

        def generate(self, *args: Any, **kwargs: Any) -> str:
            raise RuntimeError("deterministic metric attempted an LLM call")

        async def a_generate(self, *args: Any, **kwargs: Any) -> str:
            raise RuntimeError("deterministic metric attempted an LLM call")

        def get_model_name(self) -> str:
            return "offline-no-llm"

    return _NoLLM()


def trace_tool_calls(trace: Trace) -> list[Any]:
    """Convert trace tool calls (with their paired results) to DeepEval ToolCalls."""
    from deepeval.test_case import ToolCall

    results = {r.call_id: r.output for r in trace.of_type(ToolResultEvent) if r.call_id}
    return [
        ToolCall(name=c.tool, input_parameters=c.arguments or None,
                 output=results.get(c.call_id) if c.call_id else None)
        for c in trace.tool_calls
    ]


@register_metric("deepeval_tool_correctness")
class DeepEvalToolCorrectnessMetric(Metric):
    """DeepEval's ToolCorrectnessMetric over the whole conversation.

    Opt-in (list it in ``metrics`` or ``default_metrics``). Options:
    ``check_arguments`` (default true), ``exact_match`` (default false: extra
    calls allowed), ``ordered`` (default false).

    DeepEval compares arguments by plain equality, so ``{{ refs }}`` are
    resolved first. If an expected call uses matchers ($regex etc.), DeepEval
    can't express them; arguments are then not compared here and you should
    rely on ``tool_arguments`` for that call.
    """

    name = "deepeval_tool_correctness"
    requires = frozenset({Capability.TOOL_CALLS})

    def applies_to(self, case: TestCase) -> bool:
        return False  # opt-in only

    def evaluate(self, trace: Trace, case: TestCase, ctx: MetricContext) -> MetricResult:
        try:
            from deepeval.metrics import ToolCorrectnessMetric
            from deepeval.test_case import LLMTestCase, ToolCall, ToolCallParams
        except ImportError:
            return MetricResult.not_applicable(self.name, "deepeval not installed (pip install .[deepeval])")
        tc = case.expectations.tool_calls
        if tc is None or not tc.expected:
            return MetricResult.not_applicable(self.name, "no expected tool calls in test case")

        check_args = bool(self.options.get("check_arguments", True))
        expected, notes = [], []
        for exp in tc.expected:
            args, err = safe_resolve(exp.arguments, trace, case, exp.turn)
            if err or contains_matcher(args):
                notes.append(f"{exp.tool}: arguments not compared ({err or 'uses matchers'})")
                args = None
                check_args = False
            expected.append(ToolCall(name=exp.tool, input_parameters=args or None))

        metric = ToolCorrectnessMetric(
            model=_offline_model(),
            threshold=self.threshold,
            evaluation_params=[ToolCallParams.INPUT_PARAMETERS] if check_args else [],
            should_exact_match=bool(self.options.get("exact_match", False)),
            should_consider_ordering=bool(self.options.get("ordered", False)),
            include_reason=True,
            async_mode=False,
        )
        test_case = LLMTestCase(
            input="\n".join(t.user_input for t in trace.turns),
            actual_output="\n".join(t.response_text for t in trace.turns) or "(no response)",
            tools_called=trace_tool_calls(trace),
            expected_tools=expected,
        )
        score = float(metric.measure(test_case, _show_indicator=False))
        reason = (metric.reason or "").strip()
        if notes:
            reason = f"{reason}\nNote: {'; '.join(notes)}"
        return MetricResult.from_score(self.name, score, self.threshold, reason,
                                       {"arguments_checked": check_args})
