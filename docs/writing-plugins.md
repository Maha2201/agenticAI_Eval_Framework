# Writing plugins

All four plugin types follow the same pattern: subclass the interface in `agentic_eval.interfaces`, then reference the class from `app.yaml` as `file.py:ClassName` (relative to `app.yaml`), as `package.module:ClassName`, or by a registered name.

To register by name, decorate the class and make sure its module is imported: either it is in a package exposed through the `agentic_eval.plugins` entry point group, or it is listed in `core/registry.py` built-ins.

```toml
# your package's pyproject.toml
[project.entry-points."agentic_eval.plugins"]
my_plugins = "my_package.plugins"
```

## Adapter

```python
from agentic_eval.core.trace import Capability, MessageEvent, ToolCallEvent, Turn
from agentic_eval.interfaces.adapter import Adapter

class MyAdapter(Adapter):
    capabilities = frozenset({Capability.MESSAGES, Capability.TOOL_CALLS})

    def to_turn(self, raw, *, index, user_input):
        p = raw.payload
        events = [ToolCallEvent(agent=s["agent"], tool=s["name"], arguments=s["args"])
                  for s in p["steps"] if s["kind"] == "tool"]
        events.append(MessageEvent(content=p["answer"]))
        return Turn(index=index, user_input=user_input, events=events, state_after=p.get("state", {}))
```

Checklist:

- Classify by meaning: callbacks are `HookEvent`, refused routing is a rejected `HandoffEvent`, UI instructions are `ToolResultKind.SIGNAL`.
- Pair results with calls via `call_id`.
- Parse arguments into dicts (many SDKs return JSON strings).
- Raise `AdapterError` on an unexpected shape rather than returning a half-empty turn.
- Declare only real capabilities.
- Test against recorded responses.

## Connector

```python
from agentic_eval.interfaces.connector import Connector, RawResponse

class MyConnector(Connector):
    def send(self, session, message):
        payload = my_sdk.chat(session.session_id, message)
        session.session_id = payload["thread_id"]
        return RawResponse(payload=payload)
```

Optional: `open_session`, `close_session`, `close`. Raise `ConnectorError` on transport failures.

## Metric

```python
from agentic_eval.core.registry import register_metric
from agentic_eval.core.results import MetricResult
from agentic_eval.core.trace import Capability
from agentic_eval.interfaces.metric import Metric

@register_metric("max_tool_calls")
class MaxToolCalls(Metric):
    name = "max_tool_calls"
    requires = frozenset({Capability.TOOL_CALLS})

    def evaluate(self, trace, case, ctx):
        limit = int(self.options.get("limit", 5))
        n = len(trace.tool_calls)
        return MetricResult.from_score(self.name, 1.0 if n <= limit else 0.0, self.threshold,
                                       f"{n} calls, limit {limit}")
```

Set `expectation_key` to auto-activate from an `expectations` field (adding a new field means extending `Expectations` in `core/testcase.py`), or leave it `None` and enable the metric via `default_metrics` / `metrics` with `options`.

## Judge

```python
from agentic_eval.interfaces.judge import Judge, JudgeVerdict

class MyJudge(Judge):
    def score(self, trace, *, criteria, evaluation_steps=None, name="rubric"):
        ...
        return JudgeVerdict(score=0.8, reason="...", model="my-model")
```

Metrics only call `ctx.judge.score(...)`, so swapping the judge never touches metric code.
