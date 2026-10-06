"""Adapter for openai/openai-cs-agents-demo at commit 46cc386 (plain /chat JSON API).

This file is the only airline-demo-specific code in the repository. It turns one
``/chat`` response into one normalised Turn.

Response shape (observed on the local setup)::

    {
      "conversation_id": "...",
      "current_agent": "Seat Booking Agent",
      "messages": [{"content": "...", "agent": "..."}],
      "events": [
        {"id": "...", "type": "handoff",        "agent": "...", "content": "A -> B",
         "metadata": {"source_agent": "A", "target_agent": "B"}, "timestamp": null},
        {"type": "tool_call",      "content": "<tool name>", "metadata": {"tool_args": ...}},
        {"type": "tool_output",    "content": "<str(output)>", "metadata": {"tool_result": ...}},
        {"type": "context_update", "metadata": {"changes": {...}}},
        {"type": "message",        "content": "..."}
      ],
      "context": {...full state...},
      "agents": [{"name", "description", "handoffs", "tools", "input_guardrails"}],
      "guardrails": [{"name", "input", "reasoning", "passed", "timestamp"}]
    }

Quirks handled here, so metrics never see them:

* Handoff callbacks (``on_seat_booking_handoff``) are reported as ``tool_call``
  events with null metadata. They are hooks, not model choices -> HookEvent.
* A refused second handoff appears as a ``tool_output`` with text
  "Multiple handoffs detected, ignoring this one." -> rejected HandoffEvent.
* ``tool_output`` events carry no tool name or call id. They are paired with the
  oldest unanswered tool call from the same agent.
* ``tool_args`` may be a JSON string (the raw SDK value) or a dict.
* ``display_seat_map`` returns a UI instruction, not data -> ToolResultKind.SIGNAL.
* Event timestamps are null and token usage is absent, so neither capability is
  declared; latency is measured by the framework.
* For a blocked turn ``events`` is empty and the refusal is only in ``messages``.
* Non-triggered guardrails come back as ``passed: true`` with empty reasoning,
  so a passing guardrail's reason is not evidence of a real judge decision.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agentic_eval.core.trace import (
    AgentSpec,
    Capability,
    ErrorEvent,
    GuardrailEvent,
    HandoffEvent,
    HandoffStatus,
    HookEvent,
    MessageEvent,
    StateChangeEvent,
    ToolCallEvent,
    ToolResultEvent,
    ToolResultKind,
    Turn,
)
from agentic_eval.interfaces.adapter import Adapter, AdapterError
from agentic_eval.interfaces.connector import RawResponse

_DEFAULTS: dict[str, Any] = {
    "hook_name_pattern": r"^on_.+_handoff$",
    "rejected_handoff_markers": ["Multiple handoffs detected"],
    "signal_outputs": ["DISPLAY_SEAT_MAP"],
}


def _parse_args(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"_raw": value}
        return parsed if isinstance(parsed, dict) else {"_value": parsed}
    return {"_value": value}


class OpenAICSAgentsDemoAdapter(Adapter):
    name = "openai_cs_agents_demo"
    capabilities = frozenset({
        Capability.MESSAGES,
        Capability.TOOL_CALLS,
        Capability.TOOL_RESULTS,
        Capability.TOOL_ARGUMENTS,
        Capability.HANDOFFS,
        Capability.REJECTED_HANDOFFS,
        Capability.HOOKS,
        Capability.STATE,
        Capability.GUARDRAILS,
        Capability.AGENT_MANIFEST,
        # Not provided by this app: APPROVALS, EVENT_TIMESTAMPS, TOKEN_USAGE
    })

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__({**_DEFAULTS, **(options or {})})
        self._hook_re = re.compile(self.options["hook_name_pattern"])
        self._rejected_markers = list(self.options["rejected_handoff_markers"])
        self._signals = set(self.options["signal_outputs"])

    # ------------------------------------------------------------------ turn

    def to_turn(self, raw: RawResponse, *, index: int, user_input: str) -> Turn:
        payload = raw.payload
        if not isinstance(payload, dict) or "events" not in payload:
            raise AdapterError(
                f"Expected a /chat JSON object with 'events', got {type(payload).__name__}: "
                f"{str(payload)[:200]}"
            )
        events: list[Any] = []
        pending: list[ToolCallEvent] = []
        counter = 0

        for ev in payload.get("events") or []:
            etype = ev.get("type")
            agent = ev.get("agent")
            content = ev.get("content") or ""
            meta = ev.get("metadata") or {}
            common = {"id": ev.get("id") or None, "agent": agent, "raw": ev}
            common = {k: v for k, v in common.items() if v is not None}

            if etype == "message":
                events.append(MessageEvent(content=content, **common))

            elif etype == "handoff":
                events.append(HandoffEvent(
                    source=meta.get("source_agent") or agent,
                    target=meta.get("target_agent"),
                    status=HandoffStatus.ACCEPTED, **common))

            elif etype == "tool_call":
                if not ev.get("metadata") and self._hook_re.match(content):
                    events.append(HookEvent(name=content, kind="on_handoff", **common))
                    continue
                counter += 1
                call = ToolCallEvent(tool=content, arguments=_parse_args(meta.get("tool_args")),
                                     call_id=f"t{index}-c{counter}", **common)
                events.append(call)
                pending.append(call)

            elif etype == "tool_output":
                output = meta.get("tool_result", content)
                text = str(output)
                if any(m in text for m in self._rejected_markers):
                    events.append(HandoffEvent(source=agent, target=None,
                                               status=HandoffStatus.REJECTED, reason=text, **common))
                    continue
                call = next((c for c in pending if c.agent == agent), pending[0] if pending else None)
                if call is not None:
                    pending.remove(call)
                kind = ToolResultKind.SIGNAL if text.strip() in self._signals else ToolResultKind.DATA
                events.append(ToolResultEvent(tool=call.tool if call else None, output=output,
                                              call_id=call.call_id if call else None,
                                              kind=kind, **common))

            elif etype == "context_update":
                events.append(StateChangeEvent(changes=meta.get("changes") or {}, **common))

            else:
                events.append(ErrorEvent(message=f"unrecognised event type {etype!r}", **common))

        # Blocked turns have no events; the refusal is only in `messages`.
        if not any(isinstance(e, MessageEvent) for e in events):
            for m in payload.get("messages") or []:
                if m.get("content"):
                    events.append(MessageEvent(content=m["content"], agent=m.get("agent")))

        blocked = False
        for g in payload.get("guardrails") or []:
            passed = bool(g.get("passed", True))
            blocked = blocked or not passed
            ts = g.get("timestamp")
            events.append(GuardrailEvent(
                **({"id": g["id"]} if g.get("id") else {}),
                name=g.get("name", "unknown"), passed=passed, stage="input",
                reason=g.get("reasoning") or None,
                timestamp=(ts / 1000.0) if isinstance(ts, (int, float)) else None, raw=g))

        return Turn(
            index=index,
            user_input=user_input,
            events=events,
            active_agent=payload.get("current_agent"),
            state_after=dict(payload.get("context") or {}),
            blocked=blocked,
            latency_ms=raw.latency_ms,
            raw=payload,
        )

    # -------------------------------------------------------------- manifest

    def agent_manifest(self, raw: RawResponse) -> dict[str, AgentSpec]:
        payload = raw.payload if isinstance(raw.payload, dict) else {}
        return {
            a["name"]: AgentSpec(
                name=a["name"], description=a.get("description"),
                tools=list(a.get("tools") or []), handoffs=list(a.get("handoffs") or []),
                guardrails=list(a.get("input_guardrails") or []))
            for a in payload.get("agents") or [] if a.get("name")
        }
