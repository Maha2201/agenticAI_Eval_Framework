import pytest
from pydantic import ValidationError

from agentic_eval.core.testcase import TestCase
from agentic_eval.core.trace import HandoffEvent, ToolCallEvent, Trace, Turn


def test_shorthands():
    case = TestCase.model_validate({
        "id": "x", "turns": ["hi"], "metrics": ["agent_path"],
        "expectations": {"tool_calls": {"expected": ["update_seat"]}},
    })
    assert case.turns[0].user == "hi"
    assert case.metrics[0].name == "agent_path"
    assert case.expectations.tool_calls.expected[0].tool == "update_seat"


def test_typo_in_expectation_is_rejected():
    with pytest.raises(ValidationError):
        TestCase.model_validate({"id": "x", "turns": ["hi"], "expectations": {"tool_call": {}}})


def test_trace_round_trip_and_path():
    t = Trace(application="a", entry_agent="A", turns=[Turn(index=0, user_input="q", events=[
        HandoffEvent(source="A", target="B"),
        ToolCallEvent(agent="B", tool="t", arguments={"k": 1}),
        HandoffEvent(source="B", target="A"),
    ])])
    again = Trace.model_validate_json(t.model_dump_json())
    assert again.agent_path() == ["A", "B", "A"]
    assert isinstance(again.turns[0].events[1], ToolCallEvent)
