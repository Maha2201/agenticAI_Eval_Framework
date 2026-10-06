"""LLM-judged rubric metric. The judge is pluggable; this metric never imports a provider."""

from __future__ import annotations

from agentic_eval.core.registry import register_metric
from agentic_eval.core.results import MetricResult
from agentic_eval.core.testcase import TestCase
from agentic_eval.core.trace import Capability, Trace
from agentic_eval.interfaces.metric import Metric, MetricContext


@register_metric("llm_rubric")
class LLMRubricMetric(Metric):
    """Score the conversation against free-text criteria with the configured judge.

    Use it for what can't be checked from the trace structure: did the agent
    ask for confirmation before a change, was the answer grounded in the tool
    output, was the tone appropriate. Keep deterministic checks deterministic.
    """

    name = "llm_rubric"
    expectation_key = "rubric"
    requires = frozenset({Capability.MESSAGES})
    deterministic = False

    def evaluate(self, trace: Trace, case: TestCase, ctx: MetricContext) -> MetricResult:
        rubric = case.expectations.rubric
        assert rubric is not None
        if ctx.judge is None:
            return MetricResult.not_applicable(
                self.name, "no judge configured (or --no-judge); rubric not scored"
            )
        verdict = ctx.judge.score(
            trace, criteria=rubric.criteria, evaluation_steps=rubric.evaluation_steps or None,
            name=f"{case.id}-rubric",
        )
        threshold = rubric.threshold if self.options.get("use_case_threshold", True) else self.threshold
        details = {
            "judge": ctx.judge.name,
            "model": verdict.model,
            "criteria": rubric.criteria,
            "evaluation_steps": verdict.evaluation_steps,
            "steps_source": verdict.steps_source,
        }
        if verdict.steps_source == "generated":
            details["warning"] = (
                "Judge generated its own evaluation steps from the criteria. "
                "Review them: generated steps can drift to generic quality checks. "
                "Add evaluation_steps to the test case."
            )
        return MetricResult.from_score(
            self.name, verdict.score, threshold, verdict.reason, details, deterministic=False,
        )
