# Spike 0 — LibreOffice editor go/no-go (empirical)

Throwaway empirical validation for `docs/fork/research/libreoffice-editor.md`. Run on
**2026-06-25** against the **actual Collabora engine** — `collabora/code:latest` =
**Collabora Office 26.04.1.4** (LibreOffice core; well past the `Hide_Command` ≥24.04.11.2
and the 24.8 comment-reply-order fix). All tests are **headless** (no browser), driving
Collabora's bundled `soffice` directly; fixtures are built and re-read with the fork's own
Adeu path (`adeu==1.12.1`) in the `lq-ai-api-dev` image with the repo mounted at `/repo`.

**VERDICT: GO.** Every load-bearing fidelity risk the research doc gated on came back green.

## What was tested & the result

Fixtures (built with the fork's REAL redline path — `RedlineService` / `word_diff_edits`,
ADR-F045):
- `fix1_agent_redline.docx` — clean NDA + agent (`LQ.AI Commercial counsel`) tracked changes + a comment.
- `fix2_counterparty.docx` — NDA marked up by `Opposing Counsel` + a comment.
- `fix3_multipass.docx` — **agent redline applied ON TOP of fix2** (a 2nd tracked-change pass over an already-tracked doc — the VibeLegalStudio failure scenario).
- `fix5_lawyer_plus_agent.docx` — fix1 + a NEW tracked change + comment by a DISTINCT author (`Jane Lawyer (Acme LLP)`) — represents the lawyer editing in the editor.

"Round-trip" = `soffice --convert-to "docx:MS Word 2007 XML"` through Collabora's LibreOffice
(re-serialises the whole OOXML — the same core a WOPI `PutFile` save runs). Re-read = the
fork's `extract_text_from_stream(clean_view=False)` (Adeu) + raw OOXML inspection.

| Risk (from the research doc) | Test | Result |
|---|---|---|
| **#1 author byte-string survives a save** (drives `is_ours`, exact-equality on `w:author`) | round-trip fix1/fix2/fix3/fix5; compare `w:author` before/after | **PASS** — `LQ.AI Commercial counsel`, `Opposing Counsel`, `Jane Lawyer (Acme LLP)` all preserved **verbatim**; `is_ours` intact every time |
| **#1 distinct authors coexist + discriminate** (new lawyer edit ≠ agent) | fix5: agent + lawyer authors, round-tripped | **PASS** — both authors + both comments survive; `is_ours` separates agent from lawyer, identical pre/post |
| **#2 "Remove personal information on saving" wipes authorship** (silent total-loss) | observe whether authors survive a default-config save | **PASS** — strip is **OFF by default**; authorship survived all round-trips (we still pin it OFF in coolwsd config) |
| **#11 multi-pass nesting** (`<w:ins><w:del>` corruption that sank VibeLegalStudio) | fix3 generation (2nd pass over already-tracked) + round-trip | **PASS** — `NESTED(ins>del)=0` and `NESTED(del>ins)=0` at generation AND after Collabora re-save; the fork's gate-against-clean-text + word-diff avoids it |
| **#4 Collabora-authored OOXML is a 3rd Adeu dialect** | re-read every Collabora-saved file through Adeu `read`/`extract_text_from_stream` | **PASS** — Adeu re-reads Collabora's serialised OOXML cleanly in every case |
| **comments + threads survive** | count `word/comments*.xml` before/after | **PASS** — all comments preserved (Collabora normalises `comments1.xml` → canonical `comments.xml`) |

Raw signal (post round-trip): fix1 `w:ins=3 w:del=3 nested=0 authors=[LQ.AI]` + 1 comment;
fix3 `w:ins=5 w:del=2 nested=0 authors=[LQ.AI, Opposing Counsel]` + 2 comments;
fix5 `w:ins=4 w:del=4 nested=0 authors=[Jane Lawyer (Acme LLP), LQ.AI Commercial counsel]` + 2 comments.
Full inspector output is in the session transcript. File sizes drop on round-trip (e.g.
38.9 KB → 21.4 KB) — that is LibreOffice's more compact OOXML serialisation, **not** data
loss (all changes/comments/authors verified present afterwards).

## Reproduce

```
SPIKE=<this dir's working copy>   # scripts also copied here for reference
# 1. build fixtures (dev image, repo mounted)
docker run --rm -v <repo>:/repo -v "$SPIKE":/work -w /repo/api lq-ai-api-dev python /work/make_fixtures.py
docker run --rm -v <repo>:/repo -v "$SPIKE":/work -w /repo/api lq-ai-api-dev python /work/make_lawyer_edit.py
# 2. round-trip through Collabora's LibreOffice
docker run --rm -v "$SPIKE":/work -e HOME=/tmp -u root --entrypoint bash collabora/code -c \
  '/opt/collaboraoffice/program/soffice --headless --norestore -env:UserInstallation=file:///tmp/lp \
   --convert-to "docx:MS Word 2007 XML" --outdir /work <each fixture>.docx'
# 3. inspect (exit code != 0 on Adeu-parse-failure OR nesting)
docker run --rm -v <repo>:/repo -v "$SPIKE":/work -w /repo/api lq-ai-api-dev \
  python /work/inspect_docx.py /work/rt_*.docx
```

Scripts: `make_fixtures.py`, `make_lawyer_edit.py`, `inspect_docx.py` (copied into this dir).

## Not covered here — deferred to implementation slices (honest scope)

- **Collabora's WOPI session assigning the editing user's `UserFriendlyName` as the new
  edit's `w:author`.** The headless command-line Basic-macro dispatch silently no-op'd in
  `--invisible` mode (a known finicky path), so we proved the equivalent via Adeu-authored
  distinct authors instead (fix5). The WOPI→`UserName`→`w:author` chain is documented
  coolwsd behaviour and was working in the maintainer's earlier **VibeLegalStudio** project
  (it set `UserFriendlyName` and relied on it). → **confirm in Slice 1/2** when the real
  WOPI host + coolwsd are up. Low residual risk: the *fidelity* half (any author string
  survives a save) is proven here.
- **The reskin hide surface** (`Hide_Command`/`Hide_Button`/`ui_defaults`/`Insert_CSS`
  actually clearing chrome on this build) needs a live coolwsd + browser. VibeLegalStudio
  already demonstrated the 3-layer reskin empirically; → **confirm in Slice 4** on the
  pinned build (issue #13224 watch).
- **Tracked MOVES** (tdf#149707 class) and comment-id renumbering across a real interactive
  edit — fold the fork's C5a/C5b fidelity corpus through coolwsd in Slice 2/3.

## Pinned outcome

Engine validated: **Collabora Office 26.04.1.4** (`collabora/code:latest` on 2026-06-25).
For production, **pin** an explicit tag at/after this and re-run this spike on every bump.
Decision: **GO** — proceed to Slice 1 (self-built `collabora` service + proxy + NOTICES).
