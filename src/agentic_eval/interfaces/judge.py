"""Judge interface: LLM-based scoring with a swappable model provider.

Metrics that need judgement call ``judge.score(...)`` and never import a
provider SDK or DeepEval directly, so the judge implementation (DeepEval G-Eval
today, something else tomorrow) can change without touching metrics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agentic_eval.core.trace import Trace


@dataclass
class JudgeVerdict:
    score: float  # 0.0 – 1.0
    reason: str = ""
    model: str = ""
    #: Steps the judge actually scored against, for audit.
    evaluation_steps: list[str] = field(default_factory=list)
    #: "provided" (from the test case) or "generated" (written by the judge model).
    steps_source: str = "provided"
    raw: dict[str, Any] = field(default_factory=dict)


class Judge(ABC):
    name: str = "judge"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options = options or {}

    @abstractmethod
    def score(
        self,
        trace: Trace,
        *,
        criteria: str,
        evaluation_steps: list[str] | None = None,
        name: str = "rubric",
    ) -> JudgeVerdict:
        """Score the whole conversation in ``trace`` against ``criteria``."""

    @property
    def model_name(self) -> str:
        return str(self.options.get("model", "unknown"))
