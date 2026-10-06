"""Result models produced by metrics and the runner."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from agentic_eval.core.trace import Trace


class MetricStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"  # adapter can't observe what the metric needs
    ERROR = "error"  # the metric itself crashed (harness problem, not an app failure)


class MetricResult(BaseModel):
    name: str
    status: MetricStatus
    score: float | None = None  # 0.0 – 1.0
    threshold: float | None = None
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    deterministic: bool = True

    @property
    def passed(self) -> bool:
        return self.status == MetricStatus.PASSED

    @classmethod
    def from_score(
        cls,
        name: str,
        score: float,
        threshold: float,
        reason: str = "",
        details: dict[str, Any] | None = None,
        deterministic: bool = True,
    ) -> "MetricResult":
        return cls(
            name=name,
            status=MetricStatus.PASSED if score >= threshold else MetricStatus.FAILED,
            score=round(score, 4),
            threshold=threshold,
            reason=reason,
            details=details or {},
            deterministic=deterministic,
        )

    @classmethod
    def not_applicable(cls, name: str, reason: str) -> "MetricResult":
        return cls(name=name, status=MetricStatus.NOT_APPLICABLE, reason=reason)

    @classmethod
    def error(cls, name: str, reason: str) -> "MetricResult":
        return cls(name=name, status=MetricStatus.ERROR, reason=reason)


class CaseStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"  # a metric breached its threshold
    ERROR = "error"  # the run could not complete (connector/adapter/metric error)


class TestCaseResult(BaseModel):
    __test__ = False

    test_case_id: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    status: CaseStatus
    metrics: list[MetricResult] = Field(default_factory=list)
    error: str | None = None
    trace: Trace | None = None
    duration_ms: float | None = None


class RunSummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    metric_pass_rates: dict[str, float] = Field(default_factory=dict)


class RunResult(BaseModel):
    run_id: str
    application: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    framework_version: str = ""
    results: list[TestCaseResult] = Field(default_factory=list)
    summary: RunSummary = Field(default_factory=RunSummary)

    def summarise(self) -> RunSummary:
        s = RunSummary(total=len(self.results))
        per_metric: dict[str, list[bool]] = {}
        for r in self.results:
            if r.status == CaseStatus.PASSED:
                s.passed += 1
            elif r.status == CaseStatus.FAILED:
                s.failed += 1
            else:
                s.errors += 1
            for m in r.metrics:
                if m.status in (MetricStatus.PASSED, MetricStatus.FAILED):
                    per_metric.setdefault(m.name, []).append(m.passed)
        s.metric_pass_rates = {
            k: round(sum(v) / len(v), 4) for k, v in sorted(per_metric.items())
        }
        self.summary = s
        return s

    @property
    def exit_code(self) -> int:
        """0 = all passed, 1 = harness error, 2 = threshold breach.

        Errors win over failures: if the harness broke, the failure count
        can't be trusted.
        """
        if self.summary.errors:
            return 1
        if self.summary.failed:
            return 2
        return 0
