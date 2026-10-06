"""Common trace format.

Every adapter converts an application's native response into these models, and
every metric reads only these models. Nothing here knows about any specific
application: the event types describe concepts shared by multi-agent systems
(agents, messages, tool calls, handoffs, hooks, state changes, approvals,
guardrails), not one app's API.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


def _new_id() -> str:
    return uuid.uuid4().hex


class Capability(str, Enum):
    """What an adapter can actually observe in an application.

    Metrics declare the capabilities they need. If the adapter for an
    application cannot provide one, the metric is reported as
    ``not_applicable`` instead of failing for a reason that is not the
    application's fault.
    """

    MESSAGES = "messages"
    TOOL_CALLS = "tool_calls"
    TOOL_RESULTS = "tool_results"
    TOOL_ARGUMENTS = "tool_arguments"
    HANDOFFS = "handoffs"
    REJECTED_HANDOFFS = "rejected_handoffs"
    HOOKS = "hooks"
    STATE = "state"
    APPROVALS = "approvals"
    GUARDRAILS = "guardrails"
    AGENT_MANIFEST = "agent_manifest"
    EVENT_TIMESTAMPS = "event_timestamps"
    TOKEN_USAGE = "token_usage"


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #


class BaseEvent(BaseModel):
    """Fields shared by every event."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id)
    agent: str | None = None
    timestamp: float | None = None  # epoch seconds, only if the app reports it
    raw: dict[str, Any] | None = Field(
        default=None, description="Original event from the application, kept for debugging."
    )


class MessageEvent(BaseEvent):
    """Text produced by an agent for the user."""

    type: Literal["message"] = "message"
    content: str


class ToolCallEvent(BaseEvent):
    """A tool the model chose to call."""

    type: Literal["tool_call"] = "tool_call"
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = None


class ToolResultKind(str, Enum):
    DATA = "data"  # information returned to the model
    SIGNAL = "signal"  # an instruction for a UI or client, not data
    ERROR = "error"


class ToolResultEvent(BaseEvent):
    """The result of a tool call."""

    type: Literal["tool_result"] = "tool_result"
    tool: str | None = None
    output: Any = None
    call_id: str | None = None
    kind: ToolResultKind = ToolResultKind.DATA


class HandoffStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class HandoffEvent(BaseEvent):
    """Control passing from one agent to another.

    A rejected handoff records what the model attempted but the runtime refused
    (for example a second simultaneous handoff). It shows intent, which matters
    for routing metrics even though control did not move.
    """

    type: Literal["handoff"] = "handoff"
    source: str | None = None
    target: str | None = None
    status: HandoffStatus = HandoffStatus.ACCEPTED
    reason: str | None = None


class HookEvent(BaseEvent):
    """Framework-run code the model did not choose (callbacks, lifecycle hooks).

    Kept separate from tool calls so it never distorts tool selection metrics.
    """

    type: Literal["hook"] = "hook"
    name: str
    kind: str | None = None  # e.g. "on_handoff", "before_tool"


class StateChangeEvent(BaseEvent):
    """Changes to application or conversation state."""

    type: Literal["state_change"] = "state_change"
    changes: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequestEvent(BaseEvent):
    """The system asking a human to approve an action before it happens."""

    type: Literal["approval_request"] = "approval_request"
    action: str  # usually the tool name
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ApprovalDecisionEvent(BaseEvent):
    """A human's decision on an approval request."""

    type: Literal["approval_decision"] = "approval_decision"
    action: str
    approved: bool
    request_id: str | None = None
    decided_by: str | None = None


class GuardrailEvent(BaseEvent):
    """A guardrail check on input or output."""

    type: Literal["guardrail"] = "guardrail"
    name: str
    passed: bool
    stage: Literal["input", "output", "tool"] = "input"
    reason: str | None = None


class ErrorEvent(BaseEvent):
    """An error reported by the application during the turn."""

    type: Literal["error"] = "error"
    message: str
    code: str | None = None


Event = Annotated[
    Union[
        MessageEvent,
        ToolCallEvent,
        ToolResultEvent,
        HandoffEvent,
        HookEvent,
        StateChangeEvent,
        ApprovalRequestEvent,
        ApprovalDecisionEvent,
        GuardrailEvent,
        ErrorEvent,
    ],
    Field(discriminator="type"),
]


# --------------------------------------------------------------------------- #
# Turns, agents and traces
# --------------------------------------------------------------------------- #


class TokenUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class Turn(BaseModel):
    """One user input and everything the system did in response."""

    model_config = ConfigDict(extra="forbid")

    index: int
    user_input: str
    events: list[Event] = Field(default_factory=list)
    active_agent: str | None = Field(
        default=None, description="Agent in control when the turn ended, if reported."
    )
    state_after: dict[str, Any] = Field(
        default_factory=dict, description="Full state snapshot after the turn, if reported."
    )
    blocked: bool = Field(default=False, description="True if a guardrail stopped the turn.")
    latency_ms: float | None = Field(
        default=None, description="Measured by the framework around the connector call."
    )
    usage: TokenUsage | None = None
    raw: Any = Field(default=None, description="Raw application response for this turn.")

    # -- convenience views ------------------------------------------------- #

    def of_type(self, event_type: type[BaseEvent]) -> list[Any]:
        return [e for e in self.events if isinstance(e, event_type)]

    @property
    def response_text(self) -> str:
        return "\n".join(e.content for e in self.of_type(MessageEvent) if e.content)


class AgentSpec(BaseModel):
    """What an agent is allowed to do, when the application exposes it."""

    name: str
    description: str | None = None
    tools: list[str] = Field(default_factory=list)
    handoffs: list[str] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)


class Trace(BaseModel):
    """A complete conversation with the system under test."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(default_factory=_new_id)
    application: str
    test_case_id: str | None = None
    session_id: str | None = None
    turns: list[Turn] = Field(default_factory=list)
    agents: dict[str, AgentSpec] = Field(
        default_factory=dict, description="Agent manifest (permissions), if the app exposes one."
    )
    capabilities: set[Capability] = Field(default_factory=set)
    entry_agent: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    # -- convenience views ------------------------------------------------- #

    @property
    def events(self) -> list[Any]:
        return [e for t in self.turns for e in t.events]

    def of_type(self, event_type: type[BaseEvent]) -> list[Any]:
        return [e for e in self.events if isinstance(e, event_type)]

    @property
    def tool_calls(self) -> list[ToolCallEvent]:
        return self.of_type(ToolCallEvent)

    @property
    def handoffs(self) -> list[HandoffEvent]:
        return [h for h in self.of_type(HandoffEvent) if h.status == HandoffStatus.ACCEPTED]

    @property
    def rejected_handoffs(self) -> list[HandoffEvent]:
        return [h for h in self.of_type(HandoffEvent) if h.status == HandoffStatus.REJECTED]

    @property
    def final_state(self) -> dict[str, Any]:
        """Last reported snapshot, with any later state changes applied."""
        state: dict[str, Any] = {}
        for turn in self.turns:
            if turn.state_after:
                state = dict(turn.state_after)
            else:
                for ev in turn.of_type(StateChangeEvent):
                    state.update(ev.changes)
        return state

    def state_after_turn(self, index: int) -> dict[str, Any]:
        state: dict[str, Any] = {}
        for turn in self.turns[: index + 1]:
            if turn.state_after:
                state = dict(turn.state_after)
            else:
                for ev in turn.of_type(StateChangeEvent):
                    state.update(ev.changes)
        return state

    def agent_path(self) -> list[str]:
        """Agents that held control, in order, with consecutive repeats collapsed.

        Built from accepted handoffs. Starts with the entry agent (or the first
        handoff's source, or the first agent seen) so a conversation with no
        handoff still has a one-element path.
        """
        path: list[str] = []

        def push(agent: str | None) -> None:
            if agent and (not path or path[-1] != agent):
                path.append(agent)

        handoffs = self.handoffs
        if self.entry_agent:
            push(self.entry_agent)
        elif handoffs and handoffs[0].source:
            push(handoffs[0].source)
        for ev in self.events:
            if isinstance(ev, HandoffEvent) and ev.status == HandoffStatus.ACCEPTED:
                push(ev.source)
                push(ev.target)
            elif not path and ev.agent:
                push(ev.agent)
        return path

    def turn_of(self, event_id: str) -> int | None:
        for turn in self.turns:
            if any(e.id == event_id for e in turn.events):
                return turn.index
        return None
