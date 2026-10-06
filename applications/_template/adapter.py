"""Adapter skeleton. Map your application's response to the common trace.

Run `agentic-eval trace applications/<app> --case <id> --replay <dir>` while
developing to see exactly what the framework will receive.
"""

from __future__ import annotations

from typing import Any

from agentic_eval.core.trace import (
    AgentSpec,
    Capability,
    MessageEvent,
    ToolCallEvent,
    ToolResultEvent,
    Turn,
)
from agentic_eval.interfaces.adapter import Adapter, AdapterError
from agentic_eval.interfaces.connector import RawResponse


class MyAppAdapter(Adapter):
    name = "my_app"
    # Declare only what your app really exposes. Metrics needing anything else
    # are reported as not_applicable rather than failing.
    capabilities = frozenset({Capability.MESSAGES, Capability.TOOL_CALLS})

    def to_turn(self, raw: RawResponse, *, index: int, user_input: str) -> Turn:
        payload: Any = raw.payload
        if not isinstance(payload, dict):
            raise AdapterError(f"unexpected response: {str(payload)[:200]}")
        events: list[Any] = []
        # TODO: translate each native event into a trace event, e.g.
        # events.append(ToolCallEvent(agent=..., tool=..., arguments=..., call_id=...))
        # events.append(ToolResultEvent(tool=..., output=..., call_id=...))
        if payload.get("output"):
            events.append(MessageEvent(content=str(payload["output"])))
        return Turn(index=index, user_input=user_input, events=events,
                    state_after=payload.get("state") or {}, raw=payload)

    def agent_manifest(self, raw: RawResponse) -> dict[str, AgentSpec]:
        return {}
