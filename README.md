# agentic-eval

An evaluation framework for **agentic and multi-agent AI applications**, built to be independent of any one application.

It drives scripted conversations against a system under test, converts whatever that system returns into one **common trace format**, and scores the trace with **pluggable metrics**: which agents handled the request, which tools were called with which arguments, whether guardrails fired, what state the conversation left behind, and (where judgement is needed) an LLM-judged rubric.

The first application it is tested against is the OpenAI customer service agents demo (airline). Nothing in the core knows about airlines: that application is one folder containing a config file, an adapter and test cases.

> Status: **v0.1, core and first plugin.** Deterministic metrics, the DeepEval bridge, record/replay, and the airline demo plugin work end to end. See [Roadmap](#roadmap).

---

## Contents

- [Design principles](#design-principles)
- [How it works](#how-it-works)
- [Project structure](#project-structure)
- [Quick start](#quick-start)
- [Writing test cases](#writing-test-cases)
- [Metrics](#metrics)
- [Adding a new application](#adding-a-new-application)
- [Record and replay](#record-and-replay)
- [Reports and exit codes](#reports-and-exit-codes)
- [Configuration reference](#configuration-reference)
- [Development](#development)
- [Roadmap](#roadmap)

---

## Design principles

1. **Separate framework, own repo.** No dependency on the RAG/Gen AI evaluation framework.
2. **Application-agnostic core.** The core models concepts every multi-agent system has: agents, turns, messages, tool calls, tool results, handoffs (accepted and rejected), hooks, state changes, approvals, guardrails. Applications produce some subset of them.
3. **Everything specific sits behind an interface.** Four plugin types:

   | Plugin | Responsibility | Example |
   |---|---|---|
   | **Connector** | How to talk to an application | `http`, `replay` |
   | **Adapter** | Convert its responses into the common trace | `applications/openai_cs_agents_demo/adapter.py` |
   | **Metric** | Score a trace against a test case | `agent_path`, `tool_arguments` |
   | **Judge** | LLM-based scoring, provider swappable | `deepeval` (OpenAI, Anthropic, Ollama, …) |

4. **DeepEval inside, not underneath.** DeepEval powers `deepeval_tool_correctness` and the `deepeval` judge, but only behind the framework's own interfaces. Nothing else imports it, so it can be replaced for an application it can't handle.
5. **Deterministic first.** Most agent behaviour (routing, tool use, arguments, state, guardrails, permissions) is checked from trace structure, with no LLM. The judge is used only for what structure can't show, and is reported separately.
6. **Honest about gaps.** Adapters declare **capabilities** (what they can observe). A metric that needs something the application doesn't expose is reported as `not_applicable` with the reason, instead of passing or failing for the wrong reason.

---

## How it works

```
 test case (YAML)                         app.yaml
       │                                     │
       ▼                                     ▼
 ┌───────────┐  user turn   ┌───────────┐  raw response  ┌──────────┐
 │  Runner   │─────────────▶│ Connector │───────────────▶│ Adapter  │
 │           │◀─────────────┴───────────┘                └────┬─────┘
 │           │                 common Trace (turns + events)  │
 │           │◀───────────────────────────────────────────────┘
 │           │──▶ Metrics (deterministic) ──┐
 │           │──▶ Metrics ──▶ Judge (LLM) ──┼──▶ RunResult ──▶ run.json, report.md, exit code
 └───────────┘                              ┘
```

For each test case the runner:

1. opens a session with the **connector**;
2. for each scripted user turn, resolves `{{ state.x }}` references from the conversation so far, sends it, and times the call;
3. hands the raw response to the **adapter**, which returns a normalised `Turn`;
4. after the last turn, selects metrics (app defaults, plus any whose expectation is present in the case, plus explicit overrides), skips those whose required capabilities are missing, and runs the rest;
5. records pass / fail / not applicable / error per metric and per case.

---

## Project structure

```
agentic-eval/
├── pyproject.toml                    # package, extras: [deepeval], [dev]; CLI entry point
├── .env.example                      # environment variables (copy to .env)
├── README.md
├── docs/
│   ├── architecture.md               # design decisions and data flow
│   ├── trace-format.md               # common trace format reference
│   ├── test-case-reference.md        # every test case field
│   └── writing-plugins.md            # connectors, adapters, metrics, judges
├── src/agentic_eval/
│   ├── core/                         # knows nothing about any application
│   │   ├── trace.py                  # common trace format (events, turns, trace)
│   │   ├── testcase.py               # test case schema + loader
│   │   ├── matching.py               # {{ refs }} and $matchers
│   │   ├── config.py                 # application config (app.yaml) + env substitution
│   │   ├── registry.py               # plugin registry (names, module:Class, file.py:Class, entry points)
│   │   ├── results.py                # metric / case / run results, exit codes
│   │   └── runner.py                 # orchestration
│   ├── interfaces/                   # the four plugin contracts
│   │   ├── connector.py
│   │   ├── adapter.py
│   │   ├── metric.py
│   │   └── judge.py
│   ├── connectors/                   # generic connectors
│   │   ├── http.py                   # any JSON chat API, templated body, session id, CA bundle
│   │   └── replay.py                 # replay + recording wrapper
│   ├── metrics/                      # built-in metrics
│   │   ├── trajectory.py             # agent_path
│   │   ├── tools.py                  # tool_selection, tool_arguments, forbidden_tools, tool_scope
│   │   ├── state.py                  # final_state, final_response
│   │   ├── safety.py                 # guardrails, rejected_handoffs, approval_before_write
│   │   ├── operational.py            # latency
│   │   ├── deepeval_metrics.py       # deepeval_tool_correctness
│   │   └── rubric.py                 # llm_rubric (uses the judge)
│   ├── judges/
│   │   └── deepeval_judge.py         # ConversationalGEval, provider swappable; static judge for tests
│   ├── reporting/writers.py          # run.json, report.md, console
│   └── cli.py                        # agentic-eval run | validate | trace | plugins
├── applications/                     # one folder per system under test (plugins, not core)
│   ├── _template/                    # copy this to add an application
│   └── openai_cs_agents_demo/
│       ├── app.yaml                  # connector, adapter, judge, tool side effects, default metrics
│       ├── adapter.py                # the only airline-specific code
│       ├── testcases/*.yaml
│       ├── fixtures/                 # recorded responses for offline runs
│       └── README.md
└── tests/                            # unit + end-to-end tests (run offline, no API keys)
```

---

## Quick start

Requires Python 3.11+ (tested on 3.12).

**Windows (PowerShell)**

```powershell
cd agentic-eval
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[deepeval,dev]"
copy .env.example .env      # then edit .env
```

**macOS / Linux**

```bash
cd agentic-eval
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[deepeval,dev]"
cp .env.example .env
```

**1. Check everything loads**

```bash
agentic-eval plugins
agentic-eval validate applications/openai_cs_agents_demo
```

**2. Run offline from the bundled fixtures (no app, no API key)**

```bash
agentic-eval run applications/openai_cs_agents_demo \
  --replay applications/openai_cs_agents_demo/fixtures --no-judge
```

Expected: 3 of 4 cases pass, and `multi-intent-routing` fails on `rejected_handoffs`. That failure is deliberate: it is the rejected-handoff behaviour seen during exploration. Exit code is `2`.

**3. Run live against the airline demo**

Start the demo backend (see its runbook), then:

```bash
agentic-eval run applications/openai_cs_agents_demo --record recordings/airline
```

This runs live, scores the results, and saves every raw response so the same run can be replayed later. To include the LLM-judged rubric, set `OPENAI_API_KEY` (or switch the judge provider) and drop `--no-judge`.

**4. Inspect what the framework sees**

```bash
agentic-eval trace applications/openai_cs_agents_demo --case seat-change-happy-path \
  --replay recordings/airline
```

Prints the normalised trace as JSON. This is the main tool when writing or debugging an adapter.

Behind Zscaler or another inspecting proxy, export your root CA as PEM and set `AGENTIC_EVAL_CA_BUNDLE` in `.env`; the HTTP connector uses it for TLS verification.

---

## Writing test cases

A test case is a scripted conversation plus expectations. Metrics switch on automatically when their expectation is present.

```yaml
id: seat-change-happy-path
description: Customer changes their seat over two turns.
tags: [seat, write, multi-turn, smoke]
turns:
  - Can I change my seat?
  - Change it to 23A
expectations:
  agent_path:
    sequence: [Triage Agent, Seat Booking Agent]
    mode: subsequence            # exact | prefix | subsequence | contains
    forbidden: [Cancellation Agent]
  tool_calls:
    expected:
      - tool: update_seat
        turn: 1
        arguments:
          confirmation_number: "{{ state.confirmation_number }}"   # generated at runtime
          new_seat: {$ci: "23A"}
    forbidden: [cancel_flight]
  final_state:
    seat_number: {$ci: "23A"}
    confirmation_number: {$regex: "^[A-Z0-9]{6}$"}
  final_response:
    contains: "23A"
  latency:
    max_turn_ms: 30000
  rubric:                        # the only LLM-judged check
    criteria: >
      Before changing the seat, the assistant confirms the change with the customer.
    threshold: 0.7
metrics:
  - deepeval_tool_correctness    # opt-in extras, or {name: x, threshold: y, enabled: false}
```

**Runtime values.** Agentic apps generate values while running (booking references, ticket ids), so expectations can reference them instead of hard-coding:

| Reference | Resolves to |
|---|---|
| `{{ state.key }}` | conversation state (for tool arguments: state after the turn of the call) |
| `{{ vars.key }}` | the case's own `vars:` |
| `{{ env.NAME }}` | an environment variable |

User turns can use them too, for example `"My booking is {{ state.confirmation_number }}"`.

**Rubrics: always write `evaluation_steps`.** With only `criteria`, the judge writes its own steps, and they can drift into generic quality checks. On the airline demo, a criteria-only rubric scored a clear confirmation violation 0.91; with explicit steps (including what does *not* count) it correctly failed. `agentic-eval validate` warns about rubrics without steps.

**Matchers.** Anywhere a value is expected: `$any`, `$regex`, `$contains`, `$one_of`, `$ci`, `$gte`, `$lte`, `$absent`.

The full field list is in [docs/test-case-reference.md](docs/test-case-reference.md). Unknown fields are rejected at load time, so a typo can't silently disable a check.

---

## Metrics

| Metric | Activated by | Checks | Needs capability |
|---|---|---|---|
| `agent_path` | `agent_path` | Agents that held control, in order; forbidden agents | handoffs |
| `tool_selection` | `tool_calls.expected` | Expected tools called (count, turn, order); optional no-extras | tool_calls |
| `tool_arguments` | `tool_calls.expected[].arguments` | Arguments with refs and matchers | tool_calls, tool_arguments |
| `forbidden_tools` | `tool_calls.forbidden` | None of these tools called | tool_calls |
| `tool_scope` | default metric | Calls and handoffs within each agent's permissions | agent_manifest |
| `final_state` | `final_state` | End state values | state |
| `final_response` | `final_response` | Last response text: contains / not_contains / regex | messages |
| `guardrails` | `guardrails` | Blocked turns; which guardrails tripped | guardrails |
| `rejected_handoffs` | `handoffs` or default | Handoffs the runtime refused | rejected_handoffs |
| `approval_before_write` | `approvals` or default | Write tools preceded by an approved request | approvals |
| `latency` | `latency` | Slowest turn and total, measured by the framework | none |
| `deepeval_tool_correctness` | opt-in | DeepEval `ToolCorrectnessMetric`, offline | tool_calls |
| `llm_rubric` | `rubric` | Judge score against free-text criteria | messages + judge |

Hooks (framework callbacks such as `on_seat_booking_handoff`) are a separate event type and never count as tool calls, so they can't distort tool metrics.

---

## Adding a new application

No core changes. For example, the LangGraph customer support agent or tau-bench:

1. Copy `applications/_template/` to `applications/<new_app>/`.
2. In `app.yaml`, configure the connector (usually `http`; write a connector only for a new transport), list tools with their side effects, and pick default metrics.
3. In `adapter.py`, map the app's response into trace events and declare the capabilities it really provides.
4. Run once live with `--record`, check the result with `agentic-eval trace`, then write test cases.
5. Add adapter tests against the recordings, like `tests/test_demo_adapter.py`.

Custom connectors, metrics and judges are written the same way: subclass the interface and reference it as `file.py:ClassName` in `app.yaml`, or register it by name. See [docs/writing-plugins.md](docs/writing-plugins.md).

---

## Record and replay

| Flag | Effect |
|---|---|
| *(none)* | Live run against the application |
| `--record DIR` | Live run, and every raw response saved to `DIR/<case_id>/turn_<n>.json` |
| `--replay DIR` | No application needed; responses served from `DIR` |

Replay checks that each scripted message matches the recorded one, so an edited case can't silently score against an old response. Use replay for CI, for adapter and metric development, and to re-score old runs after a metric changes.

---

## Reports and exit codes

Each run writes `reports/<app>_<timestamp>_<run_id>/` with:

- `run.json`: everything, including every trace and metric detail (`--keep-raw` adds raw responses);
- `report.md`: readable summary, metric pass rates, per-case tables, agent path and tool calls.

| Exit code | Meaning |
|---|---|
| `0` | All cases passed |
| `1` | Harness error (connector, adapter or metric failed); results can't be trusted |
| `2` | At least one metric breached its threshold |

Metric statuses are `passed`, `failed`, `not_applicable` (the adapter can't observe what it needs, or no judge) and `error`. Judge-based results are flagged as non-deterministic in the report.

**Judge audit.** For every LLM-judged metric, `report.md` has a *Judge audit* block, and `run.json` has the same fields under the metric's `details`: judge and model, criteria, the exact evaluation steps the judge scored against, whether those steps were `provided` by the test case or `generated` by the judge, and the full reason. Generated steps are flagged with a warning in the console and the report.

---

## Configuration reference

`app.yaml` supports `${VAR}` and `${VAR:-default}` substitution; keep secrets in the environment.

| Key | Purpose |
|---|---|
| `name`, `description`, `version` | Identity of the system under test (pin the commit) |
| `connector` | `plugin` + `options` |
| `adapter` | `plugin` + `options` |
| `judge` | optional; `plugin: deepeval` with `provider` (`openai`, `anthropic`, `ollama`, `azure_openai`, `gemini`, `litellm`, `bedrock`), `model`, `temperature`, `base_url` |
| `entry_agent` | First agent, so a conversation without handoffs still has a path |
| `tools` | `tool: {side_effect: read \| write \| ui}`; `write` tools are what `approval_before_write` guards |
| `default_metrics` | Metrics run on every case |
| `testcases` | Default test case folder |

---

## Development

```bash
pytest                 # 39 tests, offline, no API keys
pytest --cov=agentic_eval
```

DeepEval is pinned to **4.2.8**, the version the bridge was checked against (class names such as `SingleTurnParams`, `MultiTurnParams` and `OpenAIModel` changed between releases). Upgrade deliberately and rerun the tests.

`DEEPEVAL_TELEMETRY_OPT_OUT=YES` is set by default.

---

## Roadmap

- **Recordings:** replace the synthetic fixtures with real ones (only the first seat-change turn is a real capture).
- **Per-turn expectations** (for example "turn 0 must not call a write tool") in addition to case-level ones.
- **Repeated runs** per case with pass@k and pass^k, since agent behaviour is non-deterministic.
- **Simulated users** (LLM-driven turns) alongside scripted turns.
- **More connectors and adapters:** LangGraph, tau-bench, OpenTelemetry / LangSmith trace import.
- **Red teaming** via DeepTeam behind the same interfaces.
- **Token usage and cost**, once an application exposes them.
- **JUnit XML report** for CI dashboards; a container contract for pipeline use.
