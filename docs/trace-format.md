# Common trace format

Defined in `src/agentic_eval/core/trace.py` (Pydantic v2). A `Trace` is a list of `Turn`s; each turn is one user input and the ordered events produced in response.

## Trace

| Field | Meaning |
|---|---|
| `application`, `test_case_id`, `session_id` | identity |
| `turns` | ordered turns |
| `agents` | agent manifest: `name → {tools, handoffs, guardrails}` (permissions) |
| `capabilities` | what the adapter can observe |
| `entry_agent` | first agent in control |
| derived | `events`, `tool_calls`, `handoffs`, `rejected_handoffs`, `final_state`, `state_after_turn(i)`, `agent_path()` |

## Turn

`index`, `user_input`, `events`, `active_agent`, `state_after` (full snapshot if the app reports one), `blocked` (a guardrail stopped the turn), `latency_ms`, `usage`, `raw`. Derived: `response_text`.

## Events

Every event has `id`, `type`, `agent`, `timestamp` (if reported) and `raw` (kept only with `--keep-raw`).

| `type` | Fields | Use it for |
|---|---|---|
| `message` | `content` | text to the user |
| `tool_call` | `tool`, `arguments`, `call_id` | a tool the **model chose** |
| `tool_result` | `tool`, `output`, `call_id`, `kind` (`data` / `signal` / `error`) | the call's result; `signal` = UI instruction, not data |
| `handoff` | `source`, `target`, `status` (`accepted` / `rejected`), `reason` | control moving between agents, or an attempt the runtime refused |
| `hook` | `name`, `kind` | framework code the model didn't choose (callbacks) |
| `state_change` | `changes` | partial state updates |
| `approval_request` | `action`, `details`, `request_id` | system asking a human before acting |
| `approval_decision` | `action`, `approved`, `request_id`, `decided_by` | the human's answer |
| `guardrail` | `name`, `passed`, `stage` (`input` / `output` / `tool`), `reason` | guardrail checks |
| `error` | `message`, `code` | errors reported by the app, or unrecognised events |

## Capabilities

`messages`, `tool_calls`, `tool_results`, `tool_arguments`, `handoffs`, `rejected_handoffs`, `hooks`, `state`, `approvals`, `guardrails`, `agent_manifest`, `event_timestamps`, `token_usage`.

Declare only what the application truly exposes.
