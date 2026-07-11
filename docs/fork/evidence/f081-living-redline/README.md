# ADR-F081 living redline — live verification record (2026-07-11, PR #267)

**Claim proven end-to-end on the dev stack with real gateway LLM runs:** round 1 creates
`MSA-Helios-Cloud (redlined).docx`; a follow-up round on the same thread redlines further and
**updates the same file row in place** — same id, same filename, `updated_at` stamped,
`created_by_run_id` repointed to the newest run, tracked changes accumulated — **no
"(redlined v2)" sibling**. Rig: throwaway probe member user on the live dev org (hard-swept to
zero rows + storage objects afterwards), rebuilt api/arq/ingest/web images carrying the slice.

## The six assertions (all PASS)

| # | Assertion | Result |
|---|---|---|
| 1 | Still exactly one "(redlined)" file after round 2; no "(redlined v2)" | PASS (2 files total: original + living redline) |
| 2 | Same row id across rounds | PASS (`411c8e8e-…`) |
| 3 | `updated_at` non-null after the in-place update | PASS (`2026-07-11T16:11:57Z`) |
| 4 | `created_by_run_id` = the run that last wrote the bytes | PASS (repointed run 1 → run 3) |
| 5 | Tracked changes accumulate | PASS — w:ins/w:del 7/8 → **12/9**; all 15 round-1 change regions **byte-preserved** in round 2 |
| 6 | Tool receipt says update-in-place | PASS — *"Continuing from your latest working version … updated 'MSA-Helios-Cloud (redlined).docx' in place — the living redline now carries the earlier tracked changes plus these new ones."* |

Runs: round 1 `cb533a9c` (2m26s, 42 steps, 481k tokens) → steer round `ce6fbad7` (31s — the agent
correctly found **no indemnification clause exists** in this MSA and asked before acting, the
ADR-F032 no-silent-action gate) → round 3 `dd5228b9` (2m13s, 28 steps, 498k tokens) = the
in-place update. The surgical gate visibly rejected 4 over-broad `preview_redline` batches before
the clean 3-edit apply. `start_fresh` was offered and never used.

## Files

| File | What it shows |
|---|---|
| `round1-files.json` / `round2-files.json` | matter file listing per round (ids, updated_at, created_by_run_id) |
| `round1.docx` / `round2.docx` | the living redline's bytes per round (OOXML tracked-change counts above) |
| `run1-detail.json` / `run2-detail.json` / `run3-detail.json` | full run receipts (steps, tool results, token counts) |
| `01-documents-tab.png` | Documents tab: ONE "(redlined)" row with the Redline badge beside the original |
| `02-timeline.png` | conversation timeline across the three runs |

## Deviations (on record)

1. A first round-1 attempt was orphaned by a dev-box memcg OOM of the arq worker (six parallel
   `search_documents` → ONNX embedder spike; known 6.3 GiB-box hazard, unrelated to this slice).
   Retried with a serial-tool-calls nudge; no config changes.
2. The prescribed round-2 prompt produced a clarify-first run (honest agent behavior — see above);
   the in-place claim is proven by the third run on the same thread. The follow-up chain itself is
   part of the evidence.

No passwords, tokens, or JWTs appear in this directory; the probe user, its rows (audit, runs,
checkpoints, documents, files, project, sessions) and its MinIO objects were verified deleted.
