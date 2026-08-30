# INTAKE-5a — live evidence (dev stack, 2026-08-30)

Slice: `docs/fork/plans/INTAKE-5-plan.md` § INTAKE-5a. Branch `intake-5a-inbox-surface`, dev DB at
migration 0102, api/arq-worker/ingest-worker/web rebuilt from the branch. Screenshots captured
headless (chromium via puppeteer-core) with a minted owner JWT placed in `localStorage`
(`lq_ai_auth`, the cypress precedent); no credential appears in any file here.

## What was proven

1. **Summary is written by the agent (ruling 7).** A fresh inbound email was synthesised through
   the bridge's own landing call (`POST /internal/intake/emails`, run from inside the mail-bridge
   container so the bridge token never left its env): a Contoso procurement note about a hosting
   renewal notice period. The intake run settled `awaiting_human` on new matter **NWT-COM-0013**
   with a five-bullet summary — *What they want / Their proposal / What we did / Open point /
   Proposed next step* — and a paused draft (`live_ask` present, `summary_stale=false`).
   `thread-summary.png` shows the detail opening on the summary with the chain collapsed
   ("Show the 1 email · 1 received · 0 sent").
2. **Attention-first list (rulings 1, 3).** `inbox.png`: four threads with a live ask ranked
   first (all on `ORG-COM-0011` share one conversation whose newest live run is paused —
   `bfea154a…`, the sibling requeue after INTAKE-4b's edit-send — so `live_ask` is correctly
   true for each), grey line = first summary bullet or "Agent is reading the thread", mono
   reference, badge "4" on the Inbox nav entry.
3. **Chain order (found live, fixed in `b0303f54`).** The NDA thread's two sent replies carry no
   provider timestamp (the bridge returns only the id); before the fix they sorted after every
   inbound email. After: `in 07:55 → out → in 14:33 → out` (`thread-nda.png`, chain expanded
   because the thread predates summaries).
4. **Matter Inbox tab** (`matter-inbox-tab.png`) and **admin Intake mailboxes page**
   (`admin-mailboxes.png`) render on the existing cockpit/admin shells (ruling 8).

API-level checks (owner token, `localhost:8000`): list ordering/fields as above; detail for
`dfedec48…` = 4 messages, `file_ids` resolved for `AWDC_Supplementary_Terms_of_Purchase.docx`;
cross-user 404 covered by `tests/test_intake_threads_api.py` (the dev DB has a single user).

## Not proven live

`summary_stale` (needs a run that settles without an outcome on a thread that already has a
summary) — covered by `tests/agents/test_intake_tools.py::test_safe_fail_leaves_the_previous_summary_in_place`
and the API test for the stale flag.
