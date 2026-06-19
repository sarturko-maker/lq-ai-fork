# Agent-run budget bump — live evidence (ADR-F026)

**Change:** cockpit deep-agent run budget raised from `20 steps / 300s` to `100 steps / 900s`
(arq job timeout `420s → 1020s` to keep the in-run cap firing before arq's hard kill).

**Stack:** live dev stack (api + arq-worker rebuilt on this change), model = `smart` alias →
`deepseek-v4-flash` (repointed for local testing).

## Deterministic proof — the new default reaches the live row

`POST /api/v1/agents/runs` with NO `max_steps` (cockpit default path), bound to the Privacy matter:

```
run_id: 9607d122-... ; status: running ; model_alias: smart ; max_steps: 100 ; purpose: agent_loop
```

The persisted run row carries `max_steps: 100` — the raised schema default is live (was 20 before).

## Behavioral proof — a run now runs PAST the old 20-step cap and completes

Run 1 (`live-run-1-clarify-1step.txt`): an under-specified 3-change ask. The agent **completed in 1
step** by asking for the missing required fields (vendor_role, lawful_basis, …) — a clean completion,
no register mutation. (Not a depth test; it short-circuited correctly.)

Run 2 (`live-run-2-deep-44steps.txt`): the SAME task fully specified ("do NOT ask for clarification").
Result:

```
created run afb93c5a-... (max_steps=100)
[2] status=running   steps=18  max_seq=18
[3] status=running   steps=43  max_seq=43
[4] status=completed steps=44  max_seq=44
final status: completed ; persisted steps: 44 ; error: None
step kinds: {'model_turn': 6, 'tool_call': 19, 'tool_result': 19}
```

**44 settled steps, completed cleanly with a full final answer.** Under the previous default of 20
this run would have settled `cap_exceeded` at step 20 with no answer. The cap is demonstrably lifted,
and the run finished well inside the 900s wall clock / 1020s arq backstop.

### Register side effects (verification artifacts — clearly named)
Run 2 created, in the deployment-global ROPA register (ADR-F019):
- system **VerifyCap Analytics** (`3fc6a606`)
- vendor **VerifyCap Messaging** (`047e6b55`)
- activity **VerifyCap step-budget test** (`6a14b03e`) — linked to the system, tagged Employees /
  Website Visitors + Contact data / Usage data.

These are test artifacts of this verification; retire on request (the agent is the sole register
writer, so removal is itself an agent task — ADR-F019/F023).
