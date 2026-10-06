"""Judge backed by DeepEval's ConversationalGEval, with a swappable model provider.

.. code-block:: yaml

    judge:
      plugin: deepeval
      options:
        provider: openai        # openai | anthropic | ollama | azure_openai | gemini | litellm
        model: gpt-4o
        temperature: 0
        # base_url: http://localhost:11434   (ollama / litellm)

Verified against deepeval 4.2.8 (class names changed across versions:
``SingleTurnParams`` / ``MultiTurnParams``, ``OpenAIModel``).
"""

from __future__ import annotations

import json
import os
from typing import Any

from agentic_eval.core.registry import register_judge
from agentic_eval.core.trace import ToolCallEvent, ToolResultEvent, Trace
from agentic_eval.interfaces.judge import Judge, JudgeVerdict

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

_PROVIDERS = {
    "openai": "OpenAIModel",
    "anthropic": "AnthropicModel",
    "ollama": "OllamaModel",
    "azure_openai": "AzureOpenAIModel",
    "gemini": "GeminiModel",
    "litellm": "LiteLLMModel",
    "bedrock": "AmazonBedrockModel",
}


@register_judge("deepeval")
class DeepEvalJudge(Judge):
    name = "deepeval"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self._model: Any = None

    def _build_model(self) -> Any:
        if self._model is not None:
            return self._model
        import deepeval.models as models

        provider = str(self.options.get("provider", "openai")).lower()
        cls_name = _PROVIDERS.get(provider)
        if cls_name is None:
            raise ValueError(f"Unknown judge provider {provider!r}. Known: {sorted(_PROVIDERS)}")
        cls = getattr(models, cls_name)
        kwargs = {k: v for k, v in self.options.items()
                  if k in ("model", "temperature", "base_url", "api_key") and v not in (None, "")}
        self._model = cls(**kwargs)
        return self._model

    @staticmethod
    def _turns(trace: Trace) -> list[Any]:
        from deepeval.test_case import ToolCall, Turn

        out: list[Any] = []
        for t in trace.turns:
            out.append(Turn(role="user", content=t.user_input))
            results = {r.call_id: r.output for r in t.of_type(ToolResultEvent) if r.call_id}
            calls = [ToolCall(name=c.tool, input_parameters=c.arguments or None,
                              output=results.get(c.call_id) if c.call_id else None)
                     for c in t.of_type(ToolCallEvent)]
            content = t.response_text or ("(blocked by guardrail)" if t.blocked else "(no response)")
            out.append(Turn(role="assistant", content=content, tools_called=calls or None,
                            metadata={"agent": t.active_agent, "state_after": t.state_after}))
        return out

    def score(self, trace: Trace, *, criteria: str, evaluation_steps: list[str] | None = None,
              name: str = "rubric") -> JudgeVerdict:
        from deepeval.metrics import ConversationalGEval
        from deepeval.test_case import ConversationalTestCase, MultiTurnParams

        metric = ConversationalGEval(
            name=name,
            criteria=None if evaluation_steps else criteria,
            evaluation_steps=evaluation_steps,
            evaluation_params=[MultiTurnParams.ROLE, MultiTurnParams.CONTENT,
                               MultiTurnParams.TOOLS_CALLED],
            model=self._build_model(),
            async_mode=False,
        )
        case = ConversationalTestCase(turns=self._turns(trace),
                                      scenario=criteria if evaluation_steps else None)
        score = float(metric.measure(case, _show_indicator=False))
        # After measure(), DeepEval holds the steps it actually scored against:
        # ours if we supplied them, otherwise the ones the judge model generated.
        used = list(getattr(metric, "evaluation_steps", None) or [])
        return JudgeVerdict(
            score=score, reason=metric.reason or "", model=self.model_name,
            evaluation_steps=used,
            steps_source="provided" if evaluation_steps else "generated",
            raw={"criteria": criteria, "provider": self.options.get("provider", "openai")},
        )


@register_judge("static")
class StaticJudge(Judge):
    """Returns a fixed score. For tests and dry runs only — never for real scoring."""

    name = "static"

    def score(self, trace: Trace, *, criteria: str, evaluation_steps: list[str] | None = None,
              name: str = "rubric") -> JudgeVerdict:
        return JudgeVerdict(score=float(self.options.get("score", 1.0)),
                            reason=str(self.options.get("reason", "static judge")),
                            model="static", evaluation_steps=list(evaluation_steps or []),
                            steps_source="provided" if evaluation_steps else "generated",
                            raw={"criteria": json.dumps(criteria)[:200]})
