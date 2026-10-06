# Architecture

## Layers

| Layer | Package | Knows about applications? |
|---|---|---|
| Core models and orchestration | `agentic_eval.core` | No |
| Plugin contracts | `agentic_eval.interfaces` | No |
| Generic plugins | `agentic_eval.connectors`, `metrics`, `judges` | No |
| Application plugins | `applications/<app>/` | Yes, one app each |

The dependency rule: `applications/` may import from `agentic_eval`; nothing in `agentic_eval` imports from `applications/`. Application plugins are loaded by reference from `app.yaml` (`adapter.py:ClassName`).

## Key decisions

**One trace format, many adapters.** Metrics read only `Trace`. An application's format is translated once, in its adapter, so N metrics × M applications needs M adapters, not N×M integrations.

**Events are typed by meaning, not by the source's label.** The airline demo labels a handoff callback as `tool_call`; the adapter emits a `HookEvent`, because the model didn't choose it. It reports a refused handoff as `tool_output`; the adapter emits a rejected `HandoffEvent`. Getting this right in the adapter is what keeps tool and routing metrics correct.

**Capabilities instead of silent assumptions.** Each adapter declares what it can observe (`Capability`). Each metric declares what it requires. A missing capability gives `not_applicable` with the reason. Example: the airline demo has no structured approval events, so `approval_before_write` is not applicable there; confirmation behaviour is checked by an LLM rubric instead.

**References and matchers for runtime values.** Expected values can be `{{ state.x }}` (resolved against the state after the turn of the tool call), `{{ vars.x }}` or `{{ env.X }}`, and `$regex`, `$one_of` and similar matchers. Hard-coded values would break on every run for apps that generate ids.

**DeepEval behind interfaces.** `deepeval_tool_correctness` converts the trace to DeepEval's `LLMTestCase` at the last moment; the `deepeval` judge converts it to a `ConversationalTestCase`. DeepEval's equality-based argument check can't express matchers, so the framework's own `tool_arguments` metric remains the authority on arguments and DeepEval's metric is an opt-in cross-check.

**Framework-measured latency.** Many apps don't return timings. The runner times each connector call; connectors may supply a more precise value.

**Record/replay as a first-class connector.** Recording wraps any connector. Replay makes runs reproducible and lets adapters and metrics be developed and tested offline.

**Exit codes for pipelines.** 0 pass, 1 harness error, 2 threshold breach. A harness error always wins, so a pipeline never treats a broken run as a quality verdict.

## Metric selection per case

1. `default_metrics` from `app.yaml`
2. any registered metric whose `applies_to(case)` is true (its expectation is present)
3. the case's `metrics:` list, which can add, retune (`threshold`, `options`) or disable (`enabled: false`)

## Case status

- `error` if the conversation could not run, or any metric crashed
- else `failed` if any metric failed
- else `passed` (`not_applicable` metrics do not fail a case, but are listed in the report)
