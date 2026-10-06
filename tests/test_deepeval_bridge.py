import pytest

pytest.importorskip("deepeval")

from agentic_eval.core.results import MetricStatus


def test_deepeval_tool_correctness_runs_offline(replay_runner, demo_cases, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = replay_runner.run_case(demo_cases["seat-change-happy-path"])
    m = next(x for x in r.metrics if x.name == "deepeval_tool_correctness")
    assert m.status == MetricStatus.PASSED, m.reason
    assert m.details["arguments_checked"] is False  # case uses matchers


def test_deepeval_judge_builds_conversation(replay_runner, demo_cases, monkeypatch):
    """Builds the provider model and DeepEval test case without calling the LLM."""
    from deepeval.test_case import ConversationalTestCase

    from agentic_eval.judges.deepeval_judge import DeepEvalJudge

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    judge = DeepEvalJudge({"provider": "openai", "model": "gpt-4o"})
    assert type(judge._build_model()).__name__ == "OpenAIModel"
    trace = replay_runner.execute_conversation(demo_cases["seat-change-happy-path"])
    turns = judge._turns(trace)
    case = ConversationalTestCase(turns=turns)
    assert [t.role for t in case.turns] == ["user", "assistant", "user", "assistant"]
    assert case.turns[3].tools_called[0].name == "update_seat"
