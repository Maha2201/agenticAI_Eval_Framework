"""Metric interface.

Metrics read only the common trace and the test case; they never see raw
application responses, so the same metric works for every application.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agentic_eval.core.results import MetricResult
from agentic_eval.core.testcase import TestCase
from agentic_eval.core.trace import Capability, Trace

if TYPE_CHECKING:
    from agentic_eval.core.config import ApplicationConfig
    from agentic_eval.interfaces.judge import Judge


@dataclass
class MetricContext:
    """Everything a metric may need besides the trace and test case."""

    app: "ApplicationConfig"
    judge: "Judge | None" = None
    options: dict[str, Any] = field(default_factory=dict)


class Metric(ABC):
    #: Registry name, used in configs and reports.
    name: str = "metric"
    #: Expectation field that activates this metric automatically
    #: (None = only runs when listed in the app's default_metrics or the case's metrics).
    expectation_key: str | None = None
    #: Capabilities the adapter must provide for the metric to be meaningful.
    requires: frozenset[Capability] = frozenset()
    default_threshold: float = 1.0
    deterministic: bool = True

    def __init__(self, threshold: float | None = None, **options: Any) -> None:
        self.threshold = self.default_threshold if threshold is None else threshold
        self.options = options

    def applies_to(self, case: TestCase) -> bool:
        if self.expectation_key is None:
            return False
        return getattr(case.expectations, self.expectation_key, None) is not None

    @abstractmethod
    def evaluate(self, trace: Trace, case: TestCase, ctx: MetricContext) -> MetricResult:
        """Score the trace. Return MetricResult.from_score / not_applicable."""
