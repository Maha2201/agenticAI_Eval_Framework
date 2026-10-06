"""Test case schema.

A test case is a scripted conversation plus expectations about the trace it
should produce. It is written in YAML (or JSON) and validated against these
models, so a typo in a field name is a load error, not a silently ignored check.

Expectations are application-agnostic: agent names, tool names and state keys
are just strings that the application's own adapter happens to produce.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserTurn(_Strict):
    """One scripted user message. May contain ``{{ state.x }}`` references,
    which are resolved against the state after the previous turn."""

    user: str


class PathMode(str, Enum):
    EXACT = "exact"  # path must equal the sequence
    PREFIX = "prefix"  # path must start with the sequence
    SUBSEQUENCE = "subsequence"  # sequence appears in order, gaps allowed
    CONTAINS = "contains"  # every agent in the sequence appears, any order


class AgentPathExpectation(_Strict):
    sequence: list[str] = Field(default_factory=list)
    mode: PathMode = PathMode.SUBSEQUENCE
    forbidden: list[str] = Field(
        default_factory=list, description="Agents that must never take control."
    )


class ExpectedToolCall(_Strict):
    tool: str
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Expected arguments. Values may be literals, {{ refs }} or matchers.",
    )
    arguments_match: Literal["subset", "exact"] = "subset"
    turn: int | None = Field(default=None, description="Only accept a call made in this turn.")
    min_calls: int = 1
    max_calls: int | None = None


class ToolCallExpectations(_Strict):
    expected: list[ExpectedToolCall] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    ordered: bool = Field(default=False, description="Expected calls must occur in listed order.")
    allow_unexpected: bool = Field(
        default=True, description="If false, calls to tools not listed in 'expected' fail."
    )

    @field_validator("expected", mode="before")
    @classmethod
    def _allow_bare_names(cls, v: Any) -> Any:
        # Allow `expected: [update_seat]` as shorthand for `[{tool: update_seat}]`.
        if isinstance(v, list):
            return [{"tool": x} if isinstance(x, str) else x for x in v]
        return v


class GuardrailExpectation(_Strict):
    blocked: bool | None = Field(default=None, description="Expect any turn to be blocked.")
    blocked_turns: list[int] | None = Field(default=None, description="Exactly these turns blocked.")
    tripped: list[str] = Field(default_factory=list, description="Guardrails that must fail.")
    not_tripped: list[str] = Field(default_factory=list, description="Guardrails that must pass.")


class HandoffExpectation(_Strict):
    max_rejected: int = 0


class ApprovalExpectation(_Strict):
    required_for: list[str] = Field(
        default_factory=list,
        description="Tools that need an approved request earlier in the trace. "
        "If empty, the application's write tools are used.",
    )


class LatencyExpectation(_Strict):
    max_turn_ms: float | None = None
    max_total_ms: float | None = None


class RubricExpectation(_Strict):
    """Criteria scored by an LLM judge (the only non-deterministic check)."""

    criteria: str
    evaluation_steps: list[str] = Field(default_factory=list)
    threshold: float = 0.7


class Expectations(_Strict):
    agent_path: AgentPathExpectation | None = None
    tool_calls: ToolCallExpectations | None = None
    final_state: dict[str, Any] | None = None
    final_response: dict[str, Any] | None = Field(
        default=None,
        description="Matchers against the last turn's response text, "
        "e.g. {contains: '23A'} or {regex: '...'}.",
    )
    guardrails: GuardrailExpectation | None = None
    handoffs: HandoffExpectation | None = None
    approvals: ApprovalExpectation | None = None
    latency: LatencyExpectation | None = None
    rubric: RubricExpectation | None = None


class MetricOverride(_Strict):
    """Explicitly select a metric and optionally override its threshold/options."""

    name: str
    threshold: float | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class TestCase(_Strict):
    __test__ = False  # stop pytest collecting this class

    id: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    application: str | None = Field(
        default=None, description="If set, the case only runs against this application."
    )
    vars: dict[str, Any] = Field(default_factory=dict)
    turns: list[UserTurn]
    expectations: Expectations = Field(default_factory=Expectations)
    metrics: list[MetricOverride] = Field(
        default_factory=list,
        description="Optional. By default, metrics run when their expectation is present.",
    )
    source_path: str | None = Field(default=None, exclude=True)

    @field_validator("turns", mode="before")
    @classmethod
    def _allow_bare_strings(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [{"user": x} if isinstance(x, str) else x for x in v]
        return v

    @field_validator("metrics", mode="before")
    @classmethod
    def _allow_metric_names(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [{"name": x} if isinstance(x, str) else x for x in v]
        return v


def load_test_cases(path: str | Path) -> list[TestCase]:
    """Load one file or every ``*.yaml``/``*.yml``/``*.json`` under a directory.

    A file may hold one case (a mapping) or several (a list, or a mapping with
    a ``cases`` key).
    """
    p = Path(path)
    files = sorted(
        f for pattern in ("*.yaml", "*.yml", "*.json") for f in p.rglob(pattern)
    ) if p.is_dir() else [p]
    cases: list[TestCase] = []
    seen: set[str] = set()
    for f in files:
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        if data is None:
            continue
        items = data.get("cases", [data]) if isinstance(data, dict) else data
        for item in items:
            case = TestCase.model_validate(item)
            case.source_path = str(f)
            if case.id in seen:
                raise ValueError(f"Duplicate test case id {case.id!r} in {f}")
            seen.add(case.id)
            cases.append(case)
    return cases
