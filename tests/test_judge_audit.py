"""Judge results must be auditable: steps used, where they came from, full reason."""

import copy

import pytest

from agentic_eval.core import registry
from agentic_eval.core.results import RunResult
from agentic_eval.reporting.writers import console_line, write_markdown


def rubric_result(runner, case):
    r = runner.run_case(case)
    return r, next(m for m in r.metrics if m.name == "llm_rubric")


def test_provided_steps_recorded(replay_runner, demo_cases):
    replay_runner.judge = registry.create("judge", "static", options={"score": 0.1})
    case = demo_cases["seat-change-happy-path"]
    _, m = rubric_result(replay_runner, case)
    assert m.details["steps_source"] == "provided"
    assert m.details["evaluation_steps"] == case.expectations.rubric.evaluation_steps
    assert "warning" not in m.details


def test_generated_steps_flagged(replay_runner, demo_cases):
    replay_runner.judge = registry.create("judge", "static", options={"score": 0.9})
    case = copy.deepcopy(demo_cases["seat-change-happy-path"])
    case.expectations.rubric.evaluation_steps = []
    r, m = rubric_result(replay_runner, case)
    assert m.details["steps_source"] == "generated"
    assert "warning" in m.details
    assert "judge generated its own steps" in console_line(r)


def test_report_has_full_reason_and_steps(replay_runner, demo_cases, tmp_path):
    long_reason = "Called update_seat without confirmation. " * 20  # > 300 chars
    replay_runner.judge = registry.create("judge", "static",
                                          options={"score": 0.1, "reason": long_reason})
    r, _ = rubric_result(replay_runner, demo_cases["seat-change-happy-path"])
    run = RunResult(run_id="t", application="a", results=[r])
    run.summarise()
    text = write_markdown(run, tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Judge audit: llm_rubric" in text
    assert long_reason.strip() in text
    assert "Asking which seat the customer wants does NOT count" in text


def test_deepeval_judge_captures_steps_used(replay_runner, demo_cases, monkeypatch):
    """Runs the real DeepEvalJudge code path with the LLM call stubbed out."""
    pytest.importorskip("deepeval")
    from deepeval.metrics import ConversationalGEval

    from agentic_eval.judges.deepeval_judge import DeepEvalJudge

    generated = ["Check the assistant is polite.", "Check the answer is relevant."]

    def fake_measure(self, test_case, _show_indicator=True, _in_component=False):
        if not self.evaluation_steps:          # mimic DeepEval generating steps
            self.evaluation_steps = generated
        self.score, self.reason = 0.9, "generic quality looks fine"
        return self.score

    monkeypatch.setattr(ConversationalGEval, "measure", fake_measure)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    judge = DeepEvalJudge({"provider": "openai", "model": "gpt-4o"})
    trace = replay_runner.execute_conversation(demo_cases["seat-change-happy-path"])

    v = judge.score(trace, criteria="confirm before change")
    assert v.steps_source == "generated" and v.evaluation_steps == generated

    steps = ["step one", "step two"]
    v = judge.score(trace, criteria="confirm before change", evaluation_steps=steps)
    assert v.steps_source == "provided" and v.evaluation_steps == steps
