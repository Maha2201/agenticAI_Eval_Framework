# Test case reference

Files: YAML or JSON. One case per file, a list of cases, or `{cases: [...]}`. Ids must be unique across the suite. Unknown fields are errors.

```yaml
id: string                      # required, unique
description: string
tags: [string]                  # filter with --tag / --skip-tag
application: string             # optional: only run against this app
vars: {key: value}              # usable as {{ vars.key }}
turns:                          # required; strings or {user: ...}
  - "text, may use {{ state.x }} / {{ vars.x }} / {{ env.X }}"
expectations:
  agent_path:
    sequence: [agent, ...]
    mode: exact | prefix | subsequence | contains     # default subsequence
    forbidden: [agent, ...]
  tool_calls:
    expected:                   # strings or objects
      - tool: name
        arguments: {arg: literal | "{{ ref }}" | {$matcher: ...}}
        arguments_match: subset | exact               # default subset
        turn: 0                 # only count calls in this turn
        min_calls: 1
        max_calls: null
    forbidden: [tool, ...]
    ordered: false
    allow_unexpected: true      # false + expected: [] = no tool may be called
  final_state: {key: literal | ref | matcher}
  final_response:
    contains: str | [str]
    not_contains: str | [str]
    regex: str
    case_sensitive: false
  guardrails:
    blocked: true | false       # any turn blocked
    blocked_turns: [int]        # exactly these turns blocked
    tripped: [guardrail]
    not_tripped: [guardrail]
  handoffs:
    max_rejected: 0
  approvals:
    required_for: [tool]        # default: tools with side_effect: write
  latency:
    max_turn_ms: number
    max_total_ms: number
  rubric:                       # LLM judge
    criteria: string
    evaluation_steps: [string]  # strongly recommended; without them the judge writes its own
    threshold: 0.7
metrics:                        # optional: add, retune, or disable
  - name
  - {name: x, threshold: 0.8, options: {...}, enabled: true}
```

## Matchers

| Matcher | Passes when |
|---|---|
| `{$any: true}` | key present, any value |
| `{$regex: "..."}` | full match on the string form |
| `{$contains: x}` | substring, or list membership |
| `{$one_of: [a, b]}` | equals one of them |
| `{$ci: "x"}` | case-insensitive, trimmed equality |
| `{$gte: n}` / `{$lte: n}` | numeric bound |
| `{$absent: true}` | key must not be present |

Literal comparison tolerates `"23"` vs `23` (JSON-string arguments).

## Reference resolution timing

- user turns: state after the previous turn
- tool arguments: state after the turn the call happened in
- `final_state`, `final_response`: final state
- a reference to a missing or null value fails that check with "unresolved reference"

## Writing rubric steps

Write `evaluation_steps` for every rubric. Good steps:

- locate the evidence first ("identify the turn in which X was called");
- state the check precisely;
- say what does **not** count (for example "asking which seat does not count as confirmation");
- fix the score for the clear failure case ("if X happened without Y, score 0 to 0.2").

The steps the judge actually used are recorded in `run.json` and shown in the report's *Judge audit* block.
