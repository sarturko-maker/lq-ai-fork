# Editor Slice 5 — "Done — hand back to agent" evidence (ADR-F047 Slice-5 addendum)

The last slice of the in-app Word-editor milestone closes the supervision loop: a lawyer reviews/edits
an agent redline in the embedded editor, clicks **Done — hand back**, and the agent re-reads their edits
(via the new generic `review_edited_document` tool) and continues.

## Live (headed Cypress, real stack + Collabora — `libreoffice-editor-handback.cy.ts`)

`slice5-editor-handback-{light,dark}.png` — the real Atlas redline open in the cockpit editor; our chrome
shows **"Done — hand back"** beside **Close**. (The document canvas loaded — CheckFileInfo + GetFile +
the editing websocket — but the Slice-4b fit overlay was still settling at capture under headless
automation; the hand-back affordance, the Slice-5 feature, is what these capture.)

`slice5-composer-primed.png` — **the money shot.** After hand-back the editor tears down, the
conversation is restored, and the composer is **focused + primed** with an editable instruction that
NAMES the document:

> I've reviewed and edited "02_Cirrus-Analytics-MSA-Draft (redlined) (agent draft).docx" in the editor.
> Please re-read it, incorporate my changes, and continue.

The lawyer edits/sends it via the normal chat box (maintainer's choice — no separate note field); the
existing `createRun({prompt, thread_id})` path resumes the run on the same thread, and the agent calls
`review_edited_document`. Spec passes **1/1**.

## Track-changes recording — the feasibility linchpin (probed + fixed deterministically)

The agent reads only TRACKED changes (CriticMarkup), so the lawyer's edits must be recorded as tracked
changes. **Probe finding:** an Adeu redline carries tracked *content* (`w:ins`/`w:del`) but NOT the
`<w:trackChanges/>` recording flag in `word/settings.xml` → the editor would open with "Record Changes"
**OFF** and the lawyer's edits would be untracked (invisible to `review_edited_document`).

**Fix (deterministic, in the bytes):** `redline_service.ensure_track_changes_recording` forces
`<w:trackChanges/>` ON in the redline output's `settings.xml` (surgical — only that part is rewritten,
every other part byte-identical; idempotent; graceful). Verified by 3 unit tests + the probe. The
lawyer's edits are then stamped by Collabora with the WOPI `UserFriendlyName` (`= claims.name`,
`wopi.py:214`), distinct from the agent's `DEFAULT_AUTHOR` — Spike-0 proved distinct authors survive a
Collabora save verbatim and discriminate.

## Trusted-supervisor re-read (the new agent capability)

`review_edited_document` reuses the proven Adeu parse (`read_state_of_play`) but renders a TRUSTED frame
("incorporate the lawyer's authoritative edits") — NOT the C5a untrusted-counterparty/decide-a-verdict
frame — and **filters out the agent's own still-pending redline** (author == `DEFAULT_AUTHOR`) so the
agent acts on the lawyer's input, not its own draft. Tested over a real two-author `.docx` (agent +
lawyer): the lawyer's edit + comment are surfaced, the agent's own change is not, the clean view is
always shown. (Naive single-author filter for now — the proper "who's on our team" identity model is a
flagged future slice.)

## Gates

- **API:** full suite **2775 passed / 34 skipped / 0 failed**; mypy clean (200 files); ruff (repo-root)
  clean. New: `test_review_edited_document` (11) + a composition grant test (non-Commercial area) + 3
  `test_redline_service` recording tests; the loader factor-out keeps the commercial/negotiation suites
  green.
- **Web:** svelte-check **0 errors**; vitest **973** (+ `canHandBack`/`handBackInstruction`); prettier
  clean.
- **Live:** the hand-back Cypress spec (above), 1/1.

## What is covered vs. left to a live agent run

The agent-resume chain is covered by deterministic tests: `review_edited_document` over real Adeu
two-author output (integration), granted + dispatched + audited on a matter-bound run (composition), and
the resume is the existing, heavily-tested `createRun({prompt, thread_id})` path. The full DeepSeek
end-to-end (lawyer edits live → sends → agent calls the tool) is not run here (provider cost + the ~50/50
Collabora postMessage flakiness under automation, noted since Slice 4); the live UI proof + the
deterministic mechanism proofs stand in for it, consistent with how Slice 4's edit→save was a live,
non-CI spec.
