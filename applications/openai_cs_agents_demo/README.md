# Application: openai-cs-agents-demo (airline)

The first application under test. It is a plugin: this folder is all the framework knows about it.

| | |
|---|---|
| Repo | `openai/openai-cs-agents-demo` |
| Commit | `46cc386` (Aug 2025), plain `/chat` JSON API |
| Local changes | models patched to `gpt-4o` / `gpt-4o-mini`; handoff callback lookup fixed for Agents SDK `functools.partial` (see the local setup runbook) |
| Agents | Triage, Seat Booking, Flight Status, Cancellation, FAQ |

## Files

- `app.yaml`: HTTP connector, adapter, judge, tool side effects, default metrics
- `adapter.py`: maps `/chat` responses to the common trace (quirks documented in its docstring)
- `testcases/`: four starter cases
- `fixtures/`: recorded responses for offline runs

## Fixtures

`fixtures/` holds **real recordings** from the local setup (openai-cs-agents-demo @ 46cc386, gpt-4o / gpt-4o-mini), captured with:

```bash
agentic-eval run applications/openai_cs_agents_demo --record recordings/airline --no-judge
```

and copied into `fixtures/`. Model output varies between runs, so re-record when the app, its models or a test case's turns change. Replay refuses to run a case whose scripted message differs from the recorded one.

Tests in `tests/` read these files, so they check relationships (the argument equals the state value) rather than literal runtime values.

## Observable capabilities

Provided: messages, tool calls with arguments, tool results, handoffs (accepted and rejected), hooks, state, guardrails, agent manifest.

Not provided: structured approvals, per-event timestamps, token usage. So:

- `approval_before_write` reports `not_applicable`; confirmation-before-change is scored by the `llm_rubric` in `seat_change.yaml`.
- Latency is measured by the framework around each HTTP call.
- Non-triggered guardrails come back as `passed: true` with empty reasoning, so they don't show that a guardrail judge actually ran.

## Starter cases

| Case | Purpose | Expected (fixtures) |
|---|---|---|
| `seat-change-happy-path` | multi-turn write with runtime confirmation number | deterministic checks pass; **rubric fails** with a judge (no confirmation before `update_seat`) |
| `flight-status-read-only` | read-only routing, no extra tools | pass |
| `guardrail-off-topic` | Relevance Guardrail blocks, nothing runs | pass |
| `multi-intent-routing` | two intents, second handoff rejected | **fail** on `rejected_handoffs` (known behaviour) |
