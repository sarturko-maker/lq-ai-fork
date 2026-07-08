# B-3 live verification — knowledge-collection search tool group (ADR-F067 D1)

Date: 2026-07-08 · dev stack (rebuilt api + arq-worker + ingest-worker; migration 0092
applied by the api migrator on boot) · lead-run probe script (scratchpad-only, never
committed) against `http://127.0.0.1:8000/api/v1` with a throwaway probe admin
(hard-swept by SQL afterwards — net-zero verified).

## Flow proven end to end

1. Upload a small DOCX (`b3-probe-escrow-note.docx`) carrying the marker sentence
   *"The house standard escrow release period is forty-two banking days."* →
   ingest pipeline → `ingestion_status='ready'`.
2. Create knowledge base **"B3 probe escrow knowledge"** + attach the file (204).
3. Adopt into the org Library: `POST /admin/library {kind: "knowledge", key: <kb_id>}` (204).
4. Create probe practice area (with `profile_md` — inert-area guard) and bind:
   `POST /practice-areas/b3-probe-area/knowledge-bases {knowledge_base_id}` (204).
5. Create a matter in the area; agent run (economy budget):
   *"Search the knowledge collections for the house standard escrow release period
   and quote the exact sentence you find, naming the collection it came from."*

## Assertions

| Check | Result |
|---|---|
| Run 1 settled | `completed` |
| Fenced RETRIEVED-DATA header (`Retrieved knowledge (reference DATA from your organisation's knowledge…`) in the transcript | **True** |
| Marker sentence quoted verbatim in the transcript | **True** |
| Un-adopt (`DELETE /admin/library/knowledge/{kb_id}` → 204), run 2 same prompt settled | `completed` |
| Fenced header in run-2 transcript (must be absent — fail-closed) | **False** |
| Marker in run-2 transcript (must be absent) | **False** |
| Probe output | `RESULT: PASS` |

Fail-closed proof: with the Library entry removed the `search_knowledge` group is not
composed (bound-but-unadopted ⇒ no enabled collection resolves), so the second run had
no path to the content — exactly the adoption+binding control F067 D1 pins.

## Teardown

API teardown (unbind → matter → area → KB → file), then SQL hard sweep of the probe
admin and every row it owned (agent_runs 2, documents 1, knowledge_bases 1, files 2,
projects 1, audit rows). `users` row deleted; residual queries returned zero.

## Gate summary (same tree, commit `cad00139`)

- Containerized api suite (git-archive tree, dev image, real Postgres): **3562 passed /
  42 skipped / 1 failed → fixed** (`test_knowledge_toggle_round_trip`; product fix =
  `populate_existing` on the PATCH re-read in `matter_capabilities.py` — the Core upsert
  bypasses the identity map), module re-run **15/15**, three touched modules re-run
  **81/81** ⇒ effective **3563 / 42 / 0**.
- `mypy app` in-container: **Success — no issues in 228 source files**.
- CI ruff: `ruff check api scripts` + `ruff format --check api scripts` **clean**.
