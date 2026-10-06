"""The airline adapter against the recorded fixtures."""

import json

from agentic_eval.core.trace import HandoffStatus, HookEvent, ToolResultKind
from agentic_eval.interfaces.connector import RawResponse
from conftest import DEMO


def load_turn(case, n):
    data = json.loads((DEMO / "fixtures" / case / f"turn_{n}.json").read_text())
    return RawResponse(payload=data["payload"], latency_ms=data["latency_ms"])


def test_handoff_callback_is_a_hook_not_a_tool_call(replay_runner):
    turn = replay_runner.adapter.to_turn(load_turn("seat-change-happy-path", 0), index=0, user_input="x")
    assert [h.name for h in turn.of_type(HookEvent)] == ["on_seat_booking_handoff"]
    assert not any(e.type == "tool_call" for e in turn.events)


def test_json_string_args_parsed_and_result_paired(replay_runner):
    turn = replay_runner.adapter.to_turn(load_turn("seat-change-happy-path", 1), index=1, user_input="x")
    call = next(e for e in turn.events if e.type == "tool_call")
    result = next(e for e in turn.events if e.type == "tool_result")
    # Values are generated at runtime, so check relationships, not literals.
    assert call.arguments["confirmation_number"] == turn.state_after["confirmation_number"]
    assert str(call.arguments["new_seat"]).upper() == "23A"
    assert result.call_id == call.call_id and result.tool == "update_seat"
    assert result.kind == ToolResultKind.DATA


def test_rejected_handoff_detected(replay_runner):
    turn = replay_runner.adapter.to_turn(load_turn("multi-intent-routing", 0), index=0, user_input="x")
    rejected = [e for e in turn.events if e.type == "handoff" and e.status == HandoffStatus.REJECTED]
    assert len(rejected) >= 1
    assert all(r.reason and "Multiple handoffs" in r.reason for r in rejected)


def test_blocked_turn_uses_messages_and_marks_blocked(replay_runner):
    turn = replay_runner.adapter.to_turn(load_turn("guardrail-off-topic", 0), index=0, user_input="x")
    assert turn.blocked
    assert turn.response_text.strip()  # refusal text comes from `messages`


def test_tool_calls_are_not_hooks_in_any_fixture(replay_runner):
    """Across every recorded turn: no hook is ever reported as a tool call."""
    for f in sorted((DEMO / "fixtures").rglob("turn_*.json")):
        data = json.loads(f.read_text())
        raw = RawResponse(payload=data["payload"])
        turn = replay_runner.adapter.to_turn(raw, index=0, user_input="x")
        assert not any(e.type == "tool_call" and e.tool.startswith("on_") for e in turn.events), f


def test_manifest(replay_runner):
    m = replay_runner.adapter.agent_manifest(load_turn("seat-change-happy-path", 0))
    assert m["Seat Booking Agent"].tools == ["update_seat", "display_seat_map"]
