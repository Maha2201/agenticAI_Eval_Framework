"""Extensibility: new plugins are added without touching the core."""

import httpx
import pytest

from agentic_eval.connectors.http import HttpConnector
from agentic_eval.core import registry
from agentic_eval.core.config import ApplicationConfig, PluginRef
from agentic_eval.core.results import MetricResult
from agentic_eval.core.testcase import RubricExpectation
from agentic_eval.interfaces.connector import Session
from agentic_eval.interfaces.metric import Metric, MetricContext


def test_custom_metric_registers_and_runs(replay_runner, demo_cases):
    @registry.register_metric("always_half_test")
    class Half(Metric):
        name = "always_half_test"

        def evaluate(self, trace, case, ctx):
            return MetricResult.from_score(self.name, 0.5, self.threshold)

    assert "always_half_test" in registry.available("metric")["metric"]
    m = registry.create("metric", "always_half_test", threshold=0.4)
    trace = replay_runner.execute_conversation(demo_cases["guardrail-off-topic"])
    assert m.evaluate(trace, demo_cases["guardrail-off-topic"], MetricContext(app=None)).passed


def test_file_plugin_reference(demo_app):
    cls = registry.resolve("adapter", demo_app.adapter.plugin, base_dir=demo_app.base_dir)
    assert cls.__name__ == "OpenAICSAgentsDemoAdapter"


def test_unknown_plugin_message():
    with pytest.raises(registry.PluginError, match="Registered"):
        registry.resolve("metric", "does_not_exist")


def test_http_connector_session_and_null_first_id():
    seen = []

    def handler(request):
        body = httpx.Request.read(request)
        import json
        seen.append(json.loads(body))
        return httpx.Response(200, json={"conversation_id": "abc", "events": []})

    c = HttpConnector({"base_url": "http://app", "path": "/chat",
                       "body": {"conversation_id": "{{session_id}}", "message": "{{message}}"},
                       "session_id_path": "conversation_id"})
    c._client = httpx.Client(base_url="http://app", transport=httpx.MockTransport(handler))
    s = Session(test_case_id="t")
    c.send(s, "hi")
    c.send(s, "again")
    assert seen[0] == {"conversation_id": None, "message": "hi"}
    assert seen[1]["conversation_id"] == "abc"


def test_rubric_uses_pluggable_judge(replay_runner, demo_cases):
    replay_runner.judge = registry.create("judge", "static", options={"score": 0.9})
    r = replay_runner.run_case(demo_cases["seat-change-happy-path"])
    rub = next(m for m in r.metrics if m.name == "llm_rubric")
    assert rub.passed and not rub.deterministic
