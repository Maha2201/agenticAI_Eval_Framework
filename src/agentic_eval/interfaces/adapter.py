"""Adapter interface: converts an application's raw responses to the common trace.

This is the only place that knows an application's response or trace format.
One adapter per application (or per trace format, e.g. OpenTelemetry spans,
LangSmith runs), configured by options in the application config.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agentic_eval.core.trace import AgentSpec, Capability, Turn
from agentic_eval.interfaces.connector import RawResponse


class AdapterError(ValueError):
    """The raw response did not have the shape the adapter expects."""


class Adapter(ABC):
    name: str = "adapter"

    #: What this adapter can observe. Metrics needing anything else are
    #: reported as not_applicable instead of failing.
    capabilities: frozenset[Capability] = frozenset()

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options = options or {}

    @abstractmethod
    def to_turn(self, raw: RawResponse, *, index: int, user_input: str) -> Turn:
        """Convert one raw response into one normalised turn."""

    def agent_manifest(self, raw: RawResponse) -> dict[str, AgentSpec]:
        """Agents and their permissions, if the application exposes them."""
        return {}

    def trace_metadata(self, raw: RawResponse) -> dict[str, Any]:
        """Extra metadata to attach to the trace (merged across turns)."""
        return {}
