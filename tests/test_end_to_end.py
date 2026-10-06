"""Whole pipeline on replayed fixtures, plus negative cases that must fail."""

import copy

from agentic_eval.core.testcase import MetricOverride

from agentic_eval.core.results import CaseStatus, MetricStatus
from agentic_eval.core.trace import ToolCallEvent


def by_name(result):
    return {m.name: m for m in result.metrics}


def test_suite_outcome(replay_runner, demo_cases):
    run = replay_runner.run(demo_cases.values())
    status = {r.test_case_id: r.status for r in run.results}
    assert status == {
        "seat-change-happy-path": CaseStatus.PASSED,
        "flight-status-read-only": CaseStatus.PASSED,
        "guardrail-off-topic": CaseStatus.PASSED,
        "multi-intent-routing": CaseStatus.FAILED,  # known issue, by design
    }
    assert run.exit_code == 2


def test_capability_gaps_are_not_applicable(replay_runner, demo_cases):
    r = replay_runner.run_case(demo_cases["seat-change-happy-path"])
    m = by_name(r)
    assert m["approval_before_write"].status == MetricStatus.NOT_APPLICABLE
    assert m["llm_rubric"].status == MetricStatus.NOT_APPLICABLE  # no judge
    assert m["tool_arguments"].passed and m["final_state"].passed


def test_wrong_runtime_value_fails_tool_arguments(replay_runner, demo_cases):
    case = demo_cases["seat-change-happy-path"]
    trace = replay_runner.execute_conversation(case)
    call = trace.tool_calls[0]
    call.arguments = {**call.arguments, "confirmation_number": "ZZZZZZ"}
    m = by_name_list(replay_runner.evaluate(trace, case))
    assert m["tool_arguments"].status == MetricStatus.FAILED
    assert m["tool_arguments"].score == 0.5


def test_out_of_scope_tool_fails_tool_scope(replay_runner, demo_cases):
    case = demo_cases["seat-change-happy-path"]
    trace = replay_runner.execute_conversation(case)
    trace.turns[1].events.append(ToolCallEvent(agent="Seat Booking Agent", tool="cancel_flight"))
    m = by_name_list(replay_runner.evaluate(trace, case))
    assert m["tool_scope"].status == MetricStatus.FAILED
    assert m["forbidden_tools"].status == MetricStatus.FAILED


def test_case_can_disable_and_retune_metrics(replay_runner, demo_cases):
    case = copy.deepcopy(demo_cases["multi-intent-routing"])
    case.metrics = [MetricOverride(name="rejected_handoffs", enabled=False)]
    r = replay_runner.run_case(case)
    assert "rejected_handoffs" not in by_name(r) and r.status == CaseStatus.PASSED


def by_name_list(results):
    return {m.name: m for m in results}
