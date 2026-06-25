# LibreOffice-based in-app Word editor — research

**TL;DR.** Adopt **Collabora Online (CODE/COOL), self-hosted as a new stateless Docker service, integrated over the WOPI protocol with our `api` acting as the WOPI host, and reskinned to ADR-F013 by hiding/collapsing Collabora's built-in chrome and driving the rendered canvas from our own Svelte toolbar via `postMessage` + UNO commands.** Collabora *is* LibreOffice-on-LOK — it satisfies the maintainer's "only LibreOffice is acceptable, local, no SaaS" constraint while shipping, already built, the components the alternatives would force us to reinvent: the sandboxed per-document engine, the tile protocol, the JS canvas client, and — decisively for a redline tool — the **tracked-changes + comment UI that round-trips Word markup through the same LibreOffice core Adeu already targets**. We reject the **custom LOK build** (reinvents Collabora as net-new C++ for an identical license and worse security) and **LibreOffice-WASM / ZetaOffice** (track-changes round-trip is *unverified*, ships a ~250 MB–1 GB MPL+LGPL payload to the browser — converting our clean server-side boundary into client distribution — and mandates invasive COOP/COEP isolation). On licensing this is a **net win versus the AGPL PyMuPDF obligation the fork already accepts**: the source stack is weak/file-level copyleft (MPL-2.0 for COOL, dual MPL-2.0/LGPLv3+ for the LibreOffice core, BSD `browser/`, OFL fonts) with **zero AGPL and zero network copyleft** — *but only on the self-build-from-source path*; the official prebuilt CODE binary additionally carries a proprietary executable-form EULA, proprietary Collabora trademark/CSS, and a "not for production" disclaimer. This document is decisive on the architecture and honest about the empirical unknowns (author-attribution byte-mapping, round-trip fidelity, residual canvas chrome) that a throwaway Spike 0 must close before any code ships.

> Authorship note: this is a synthesis of four parallel research dossiers and four adversarial verification passes. Every place the first-draft synthesis over-claimed, the verified truth is stated here and the original error is called out so a future reader does not re-introduce it. The most important correction: **Collabora is MPL-2.0, not AGPLv3** — one source dossier asserted AGPL and was wrong; do not propagate that claim.

## Goal & constraints

**Product goal.** After the agent redlines a `.docx` (today via the Adeu SDK — in-process Python, MIT, native Word tracked changes + comments), show the document to the lawyer **inside the tool** in an embedded editor. The lawyer can further edit, add comments, and export; OR hand the document back so the **agent resumes reading their markup** and continues negotiating. The agent can already read tracked changes + comments (C5a/C5b: `extract_counterparty_position` / `respond_to_counterparty`). The **editor is the only missing piece** — no new agent capability is required for resume.

**Hard constraints (these gate any solution).**

- **"The only acceptable solution is LibreOffice"** (maintainer). The editor must be **local / self-hosted, no SaaS.** Collabora Online is LibreOffice running headless on LibreOfficeKit (LOK) — it qualifies.
- **Custom UI.** Keep the rendered document page/canvas, but icons + look/feel must match our Vercel-style design system (**ADR-F013**: charcoal `#111` base, scarce blue accent, AI-Elements look, light + dark).
- **Copyleft posture is strict.** PyMuPDF's AGPL is treated as a server-side-only obligation in `NOTICES.md`; the team prefers no-copyleft deps and treats every license as supply-chain surface. **Any copyleft/proprietary obligation must be surfaced precisely** — which component, which license, what it obliges.
- **Auth.** Every endpoint authz'd; cross-user access returns **404, never 403** (no existence leak). Provider keys live **only in the gateway**. Treat retrieved/edited documents as **untrusted input** (prompt-injection / malformed-OOXML class).
- **Dev-stack discipline.** Services are docker; **never `docker compose down -v`**; migrations rebuild `api` + workers; the `web` container serves a pre-built bundle (rebuild before debugging UI); prune dangling images after each build (Crostini/btrfs disk pressure).

## Recommended architecture

A new **`collabora` compose service** (CODE) renders each `.docx`. Our **`api` is the WOPI host**: it mints a short-TTL, single-file-scoped WOPI token, serves the document bytes, holds the edit lock, and persists save-backs as new `File` rows. The cockpit gains an **`editor` matter tab** that frames Collabora's canvas but wraps it in **our own Svelte toolbar** (Vercel chrome), hides Collabora's chrome where the API allows and covers the residual strip where it does not, and drives editing actions via `postMessage`/`Send_UNO_Command`. Hand-back saves, then re-enters the existing agent loop on the same `thread_id`; the agent re-reads the lawyer's tracked changes + comments through the **identical Adeu path counterparties already use (C5a)** — zero new agent backend code.

Why this shape:

- **It reuses every real fork seam.** Cross-user-404 chokepoint (`_load_visible_file`), storage bytes path (`stream_download` / `upload_bytes`), redline provenance write pattern (flush-before-PUT), JWT type-tag pattern (`_TYPE_MFA` → new `_TYPE_WOPI`), bare-router mount (mirrors `word_addin.public_router`), and the no-remount cockpit tab idiom all exist today.
- **It keeps the gateway invariant intact.** Nothing in the editor data plane calls an LLM. Collabora gets **no gateway reachability**. The WOPI token is a `jwt_secret`-signed app token, not a provider key, and never touches the gateway. Agent resume re-enters inference only through the existing `POST /agents/runs` → worker → gateway path.
- **It contains copyleft to one unmodified, separate container** — the same boundary *shape* as the accepted PyMuPDF row, but lighter (weak/file-level, not strong+network).

## Options compared

| Criterion | **Collabora Online / CODE** (recommended) | LibreOffice-WASM (ZetaOffice) | Custom LOK build |
|---|---|---|---|
| Maturity | **Production-grade engine; years of multi-person eng; widely deployed (Nextcloud).** ✅ | Open beta (v1.x, 2024–2025); GA not delivered | Greenfield; perpetually chasing LOK's unstable C++ API |
| Editing + track-change fidelity | **Real LibreOffice core; tracked-changes + comment UI ships built-in** ✅ | Same engine → same engine fidelity, BUT **track-change round-trip UNVERIFIED in WASM** ⚠ (spike) | Same engine, **zero UI** — build comment/change UI from raw callback geometry |
| Reskinnability to our UI | Reskin lives in our Svelte DOM; hide/collapse chrome + custom toolbar via postMessage/UNO; **residual in-canvas chrome (context menu, dialogs, tooltips, comment margin) stays LO-rendered** | "standalone canvas, zero native UI" mode is **UNVERIFIED** (was over-claimed as the WASM "win") | Total control, total cost |
| License / copyleft fit | **Weak/file-level (MPL-2.0 COOL, dual MPL/LGPLv3+ core), server-side, separate container — no taint on our code; NO AGPL** ✅ | MPL+LGPL **shipped to the browser = client distribution** (heavier; LGPL relink obligations) | MPL-2.0/LGPLv3+ server-side ✅ — same as Collabora, **no licensing advantage** |
| Local-hosting fit | **One stateless compose service, no SaaS** ✅ | Fully client-side, no server ✅ | Self-hosted C++ daemon ✅ but bespoke |
| Integration effort | **Moderate — WOPI host (~5 endpoints) on existing File/auth/storage seams** ✅ | High — COOP/COEP rework of `web`; in-process JS bridge; new untrusted-frame model | **Extreme** — reinvent WSD/ForKit/Kit/TileCache/JS client/comment UI |
| Ops footprint | ~1.5–2 GB RAM/doc; large image (~ several GB; trim dictionaries); **free CODE caps at 10 docs / 20 connections + "not for production"** | ~250 MB–1 GB **per browser tab**; tens-of-seconds cold start; single-user | New C++ build + engine + security ownership forever |

**Verdict.** Collabora wins maturity, fidelity (built-in tracked-changes/comment UI), integration effort, and ops simplicity; ties on server-side license posture and local-hosting; **loses only on reskinnability** — and that is the *least* load-bearing loss because (a) our reskin lives in our own Svelte DOM regardless, and (b) the alternatives pay for that one win with showstoppers: WASM = unverified fidelity + invasive isolation + client-side license distribution; custom LOK = rebuild everything for the same license.

> **Verifier correction (reskin):** the WASM "standalone = canvas with zero chrome + your toolbar" cell was asserted as a confirmed WIN in the first draft. No primary source confirms a turnkey zero-chrome standalone mode in ZetaOffice; it is **UNVERIFIED**. It does not change the decision (WASM is rejected anyway) but must not be cited as fact.

## Prior art — VibeLegalStudio (an earlier Collabora/WOPI build by the maintainer)

The maintainer's earlier project **VibeLegalStudio** (`github.com/sarturko-maker/VibeLegalStudio` — old, partly working; treated as **evidence, not gospel**) **already implemented exactly the recommended path: Collabora Online (CODE) via a custom WOPI host, with the chrome reskinned** — and the view/edit path *worked*. This materially de-risks the decision: the hard "does Collabora-via-WOPI-with-a-custom-skin even function?" question has a working precedent in the maintainer's own code. Investigated independently (full tree + git history; clone retained at `scratchpad/VibeLegalStudio` for lifting specific code).

**What it confirms works (a reusable recipe, not just a claim):**

- **Engine choice matches.** `collabora/code` Docker service on `:9980`, chosen over raw `soffice`/LOKit/WASM/OnlyOffice (none of those appear anywhere — same conclusion this doc reaches independently).
- **A real in-house WOPI host** (`backend/wopi_routes.py`): full CheckFileInfo / GetFile / PutFile + a token endpoint, in-memory token store (32-byte, 1 h TTL), path-traversal hardening. It already solves Collabora's real-world friction our Slices 2–3 will hit: the **double-slash `/contents` URL quirk, the `X-WOPI-ItemVersion` header, and the JSON `LastModifiedTime` PutFile response Collabora demands.**
- **The iframe bring-up** (`frontend/.../DocumentViewer.tsx`): a **hidden-form POST** of `access_token` + `access_token_ttl` + `ui_defaults` to `cool.html?WOPISrc=…` (POST, not query string — needed to preserve the token), then the `App_LoadingStatus`/`Document_Loaded` postMessage handshake. Validates the launch sequence in §"How it works" / Slice 4.
- **The reskin we propose — already done, and it took the same three layers §Reskin predicts:** WOPI CheckFileInfo hide-flags (HidePrint/Export/Save/Repair) + `ui_defaults` (Menubar/Toolbar/StatusBar/Sidebar/TextRuler=false) + **runtime `Insert_CSS` / `Hide_Menu_Item` after `Document_Loaded`** to nuke residual chrome (`.main-nav`, `#main-menu`, `#toolbar-up/down`, `#status-bar`, `.cool-ruler`…), while *deliberately keeping track-changes visible*. This is **empirical confirmation that "our chrome, their canvas" is achievable in free CODE** — and a ready CSS/postMessage recipe. Consistent with our §Reskin caveat, they used CSS to **cover** the residual toolbar strip rather than delete it ("collapsed-and-covered, not removed").
- **Docker configs for dev/prod/Electron** (the `aliasgroup1` WOPI allow-list, `ssl.termination` at the proxy, the `/hosting/discovery` healthcheck) — a head-start for Slice 1.

**The single most valuable lesson — the AI-write vs editor-save race, with a working mitigation.** Their backend marks a file "modified by AI" and makes Collabora's `PutFile` return **HTTP 409 + `COOLStatusCode 1010` ("Document changed in storage")** within a short window, so the editor won't clobber a file the agent just redlined (`wopi_routes.py` lock helpers, called from their `session.py`). This is **independent confirmation of our Risk #6** (concurrent agent-write vs user-edit) and a *second, complementary* control to "gate hand-back on `runActive`": **the WOPI layer itself can refuse a stale save via 409/1010.** Adopt both — the `runActive` gate prevents the race; the 409/1010 is the backstop if it slips.

**What did NOT work — and what it means for us:**

- **Multi-pass redlining broke (the central failure).** Re-parsing a `.docx` that already had tracked changes produced **nested `<w:ins><w:del>…</w:del></w:ins>` that Word/LibreOffice cannot render** (`SUPERDOC_FINDINGS.md`, their `CLAUDE.md`/`ARCHITECTURE_REPORT.md`); their fixes were self-described "band-aids," and this is what pushed them toward an (unfinished) in-memory editor. **This is the most important risk to check against our own path**, because the editor round-trip means the agent will, on hand-back, redline a document that already carries the lawyer's *and its own prior* tracked changes. Whether the fork's Adeu word-diff renderer (ADR-F045) avoids this nesting failure is being verified directly — see **Risk #11**.
- **SuperDoc (ProseMirror) headless co-editing never finished** — stubbed, default-off (`USE_SUPERDOC=false`), fragile JSDOM export. Reinforces "do **not** build a second editor engine" — Collabora is the engine.
- **Licensing was never addressed** — no LICENSE/NOTICES/trademark handling for the bundled Collabora image at all. Directly validates our §Licensing insistence on the NOTICES row and the self-build-for-clean-posture decision; the obligation this doc names is exactly the gap the prior project shipped with.
- **DEBUG prints/logging left in the WOPI/redline paths** (file-path/content leak risk) — a reminder to hold our counts-only audit + no-secrets-in-logs discipline.

**Net:** VibeLegalStudio is a working proof the recommended architecture is buildable, plus a concrete WOPI-host + reskin recipe and a battle-tested write-conflict mitigation — while also flagging the two traps we must not repeat (multi-pass nesting; the licensing gap). It does **not** change the recommendation; it strengthens confidence and shortens Slices 1–4.

## How it works end-to-end

Data flow from agent redline to agent resume, on the real fork seams. Line numbers are best-effort against the current tree and may drift by ±a few lines; treat the symbol name as canonical.

1. **Agent finishes redline.** `_apply_redline` (`api/app/agents/commercial_tools.py`, ~`:484`) mints `new_file_id` (~`:508`), builds `File(owner_id, project_id, storage_path=str(id), ingestion_status="ready", created_by_run_id=run_id)` (~`:511-522`), `db.flush()` (~`:525`) **before** `storage.upload_bytes(...)` (~`:526`) to avoid orphan bytes. The redline `.docx` now lives in object storage with provenance and surfaces in the C7a Documents tab via `GET /matters/{id}/files` (`api/app/api/matter_files.py`, handler `list_matter_files` ~`:64`).

2. **User opens the editor.** In `DocumentsPanel.svelte`, an "Open in editor" button (next to Download, Button ~`:257-270`; `downloadFile` import ~`:68`) sets a new `matterTab='editor'` on `ConversationHost.svelte` (tab state ~`:121`). The editor renders in a sibling `{#if matterTab==='editor'}` block using the **same `class:hidden` no-remount pattern** as Memory/Documents (~`:526`/`:537`, mask ~`:454`) — the live SSE conversation is **not** torn down.

3. **Mint an editor session.** The frontend calls a new authed endpoint `POST /api/v1/files/{file_id}/editor-session` (under the `_active` dep group). It runs `_load_visible_file(db, file_id, user.id)` (`api/app/api/files.py:507`) first — minting is owner-checked, cross-user → **404** (the function's own docstring: *"The cross-user case is collapsed into 404 deliberately."*). It mints a short-TTL, **single-file-scoped** WOPI token (new `_TYPE_WOPI` in `api/app/security/jwt.py`, mirroring `_TYPE_MFA` at `:49`, `create_mfa_token`/`decode_mfa_token` at ~`:146`/`:164`, signed with `settings.jwt_secret`) carrying a **`file_id` claim**, and returns `{ wopiSrc, accessToken, accessTokenTtl, collaboraOrigin }`.

4. **Browser launches the iframe.** `DocumentEditorPanel.svelte` form-POSTs `access_token` / `access_token_ttl` into the iframe pointed at `<urlsrc from cached discovery.xml>?WOPISrc=<enc https://<api>/wopi/files/{id}>`. **Collabora never receives the user's session JWT** — only the file-scoped WOPI token.

5. **Collabora calls our WOPI host** (`api/app/api/wopi.py`, mounted **bare** like `word_addin.public_router` at `api/app/api/__init__.py:93`, NOT under `_active`): `CheckFileInfo` → `GetFile` (streams via `stream_download`, `api/app/storage.py:346` — the same bytes path as `get_file_content`, `files.py` ~`:431`) → `Lock`. **Every** handler re-runs `decode_wopi_token` + `_load_visible_file(db, file_id, claims.user_id)` — authz on *every* call, 404 on mismatch — and verifies the token's `file_id` claim matches the `{file_id}` in the URL (a token for file A replayed at `/wopi/files/B` → 404).

6. **User edits + comments** in the canvas, driven by our Vercel-style Svelte toolbar (see Reskin). Collabora periodically `RefreshLock`s.

7. **Save-back.** On autosave / explicit save / exit, Collabora `PutFile`s the full new `.docx` (`X-WOPI-Override: PUT`, body = bytes). Our handler verifies the lock, runs **`guard_ooxml`** on the body (reuse `app/pipeline/readers/_base.py:325`, already imported in `commercial_tools.py:54` — untrusted-input rule), writes a **new `File` row** with `created_by_run_id=None` (the provenance inverse of the agent's write: **user-authored**), `db.flush()` then `storage.upload_bytes(...)` (mirrors the redline pattern), and a counts-only `audit_action`. The new row auto-appears in the matter file list (it carries `project_id`).

8. **Agent resumes — zero new agent capability.** A "Hand back to agent" toolbar button posts `Action_Save{Notify:true}`; on `Action_Save_Resp` success it seeds the composer ("I've reviewed and edited the redline — please continue.") and `POST /api/v1/agents/runs` (`api/app/api/agent_runs.py`, handler `create_agent_run` ~`:268`) with the existing **`thread_id` only** → continues on the langgraph checkpointer. (Trap, confirmed in code: passing **both** `thread_id` and `project_id` is a **422** — send `thread_id` alone.) The matter-bound run already has `extract_counterparty_position` (`commercial_tools.py:223`) → `_extract_counterparty_position` (~`:586`) → `read_state_of_play` (`api/app/agents/negotiation_service.py:182`), which parses the saved `.docx`'s native tracked changes + comments via Adeu. **The lawyer's edits are consumed through the identical path counterparties use (C5a) — no new backend agent wiring.**

> **Verifier corrections (fit):** (a) `guard_ooxml` lives at `app/pipeline/readers/_base.py` — there is *also* an `app/agents/_base.py`, so never cite a bare `_base.py`. (b) The first draft said the WOPI lock reuses Redis "already wired via `get_stream_bridge`" — only the Redis **connection** is reusable; `get_stream_bridge` is an SSE event bridge, not a lock manager. WOPI Lock/Unlock/RefreshLock/GetLock with `409 + X-WOPI-Lock` echo is **net-new code**.

## The WOPI host we must build

New router `api/app/api/wopi.py`, mounted **bare** (auth inside each handler via the WOPI token, not the `Authorization` header). All paths under `/wopi/files/{file_id}`, where `{file_id}` = our `File.id`.

| Endpoint | WOPI op | Maps onto | Authz / behavior |
|---|---|---|---|
| `POST /api/v1/files/{id}/editor-session` *(authed, `_active`)* | session mint | `_load_visible_file` (`files.py:507`) → `create_wopi_token` | Owner-scoped; **404 on cross-user**. Returns `{wopiSrc, accessToken, accessTokenTtl, collaboraOrigin}` |
| `GET /wopi/files/{id}` | **CheckFileInfo** | `_load_visible_file(db,id,claims.user_id)` | `BaseFileName`=filename, `Size`=size_bytes, `Version`=`hash_sha256` (drives external-change detection), `OwnerId`, `UserId`, **`UserFriendlyName`=the lawyer's real name (≠ `DEFAULT_AUTHOR`)**, `UserCanWrite:true`, `PostMessageOrigin`=our web origin, `SupportsLocks:true`, `UserCanNotWriteRelative:true`. **404 on token/file mismatch** |
| `GET /wopi/files/{id}/contents` | **GetFile** | `stream_download` (`storage.py:346`) | Same authz; apply a size cap (mirror `_MAX_DOCX_BYTES` = 25 MiB, `commercial_tools.py:92`) |
| `POST /wopi/files/{id}/contents` (`X-WOPI-Override: PUT`) | **PutFile** | `guard_ooxml` (`pipeline/readers/_base.py:325`) → new `File` row + `upload_bytes` (`storage.py:457`), flush-before-PUT | Verify lock (409 + `X-WOPI-Lock` on mismatch); `created_by_run_id=None`; counts-only audit; honor `X-COOL-WOPI-IsModifiedByUser` (skip no-op versions) |
| `POST /wopi/files/{id}` (`LOCK`/`UNLOCK`/`REFRESH_LOCK`/`GET_LOCK`) | **Lock family** | Redis (connection reusable; lock semantics net-new), keyed by file_id, ~30-min TTL | On 409 **always echo current `X-WOPI-Lock`** — Collabora's state machine requires it |

**The access_token → per-user-authz → cross-user-404 guarantee (three layers):**
(a) session minting is gated by `ActiveUser` + `_load_visible_file` → 404 cross-user;
(b) the WOPI token carries a `file_id` claim and the handler asserts it equals the URL `{file_id}`, so it cannot be replayed against another file even by the same user;
(c) **every** WOPI handler re-runs `_load_visible_file(db, file_id, claims.user_id)` → `NotFound` → **404, never 403**, exactly the house rule.
The token is *not* a provider key and never touches the gateway.

**Two safety notes the spec must keep:**
- WOPI `UserCanWrite` is a **UI hint, not authorization** — `PutFile` must independently re-check write permission from the token, not trust the flag.
- Lock coolwsd's WOPI allow-list (`aliasgroup1`) to exactly the `api` origin. This is the direct mitigation for the **CVE-2025-27791** class (malicious-WOPI arbitrary file-write via `CheckFileInfo` `BaseFileName` path traversal; patched in CODE 24.04.13.1 / 23.05.19 / 22.05.25 — pinning a modern build is independently required).
- **Defer WOPI proof-key signing.** Record explicitly that the threat model relies on the file-scoped short-TTL token + the private compose network + the origin allow-list, **not** on proof-key validation.

## Reskinning to our Vercel UI

The reskin **lives in our own Svelte DOM** — that is what makes it ungated. We render the outer toolbar/header ourselves (semantic tokens, `@lucide/svelte` icons, our `button` ghost/icon idiom) and only *drive* Collabora's canvas through the documented PostMessage surface.

**What we own fully (our DOM, semantic tokens, auto light/dark):** the entire outer toolbar/header in Svelte using `web/src/app.css` tokens (`--background` `#111` dark / `#fff` light, `--brand` scarce blue, hairline `--border`), `@lucide/svelte` icons, and the `$lib/components/ui/button` ghost/icon-sm idiom (cf. `CockpitHeader.svelte` ~`:96-99`). New files: `web/src/lib/lq-ai/api/collabora.ts`, pure-tested `web/src/lib/lq-ai/.../collaboraBridge.ts` (test via `<script module>` exports — **no `@testing-library/svelte` in this repo**), `DocumentEditorPanel.svelte`, `DocumentEditorToolbar.svelte`.

**What we hide/collapse** (after waiting for `App_LoadingStatus: Document_Loaded` — sending hide calls before it is the #1 cause of "Hide doesn't work"; note read-only docs emit only `Initialized`, never `Document_Loaded`, but our editor opens writable so this is unlikely to bite): set `ui_defaults` at launch (compact/notebookbar off, ruler/statusbar/sidebar off — avoids a first-paint flash; `ui_defaults` and `css_variables` are **launch form-fields, not PostMessage ids**), then `Hide_Menubar` + `Hide_StatusBar` + `Hide_Ruler` + `Hide_Sidebar`, and prefer **`Hide_Command`** (UNO id, hides across menu + toolbar + notebookbar) over fragile id-based `Hide_Button`.

> **Verifier correction (reskin), load-bearing — keep prominent, do not bury:** there is **no `Hide_Toolbar`** in the API. The top toolbar can be **emptied/collapsed** (Hide_Command/Hide_Button per item, or the Tabbed-view collapse trick), but **a residual bar remains rendered in the canvas** — we **cover/theme it, we cannot delete it**. The honest claim is: *menubar + statusbar + ruler + sidebar are fully hideable; the toolbar is collapsed-and-covered, not removed.* Additionally, `Hide_Command` is **version-gated** (`New in version 24.04.11.2`, and only then does it also hide contextual-menu items) and has at least one open "no effect" report (issue #13224 against 25.04.6.1). **Spike 0 must prove `Hide_Command`/`Hide_Button` actually clear the intended buttons on the exact pinned build** before this section is treated as done; pin ≥ 24.04.11.2 (realistically a current 25.04.x with #13224 confirmed-fixed on the build).

**What we drive via postMessage** — our toolbar buttons fire into the canvas:

| Our control | Command |
|---|---|
| Save (disabled until `Doc_ModifiedStatus:true`) | `Action_Save{Notify:true}` |
| Undo / Redo | `Send_UNO_Command .uno:Undo` / `.uno:Redo` |
| Accept / Reject change | `.uno:AcceptTrackedChange` / `.uno:RejectTrackedChange` |
| Next / Prev change | `.uno:NextTrackedChange` / `.uno:PreviousTrackedChange` |
| Toggle track-changes (lit when on) | `.uno:TrackChanges` |
| Add comment | `.uno:InsertAnnotation` |
| Export .docx / PDF | `Action_Save` + `downloadFile(id)` (`web/src/lib/lq-ai/api/files.ts:85`) / `Action_Export{Format:pdf}` |
| **Hand back to agent** (primary `--brand`) | `Action_Save{Notify}` → on `Action_Save_Resp` → seed composer + `POST /agents/runs` (thread_id only) |

Use **`Disable_Default_UIAction`** for `UI_Save` and `UI_Close` (the docs confirm *only* these two are currently supported — exactly the two we need) so our buttons own those flows.

**Theme push.** The iframe can't read our `<html>.dark` class. Dark state is applied to the document element + a `localStorage 'theme'` key in `cockpit/helpers.ts` (`applyTheme` ~`:265`, class toggle ~`:271`) — there is **no Svelte theme store** (the iframe bridge can observe the class via `MutationObserver` *or* read the `localStorage` key). Add a small `lib/theme.ts` (`isDark()` / `observeTheme(cb)`), observe, and postMessage Collabora's dark toggle on change. Wrap the iframe in `bg-background` so letterboxing reads as our canvas.

**Residual chrome that is unavoidable** (LibreOffice-rendered inside the canvas, not host-controllable): the residual toolbar strip, right-click context menu, in-canvas tooltips, modal dialogs (font picker, find/replace), cursor/selection handles, and the comment margin. Accept these as the cost of a real engine.

**Licensing gates on the reskin — corrected.** The hide/UNO/Action PostMessage surface (hide-all + custom-toolbar-via-UNO + intercept save/close) is **fully present in free CODE with no documented license gate** (widely used in free Nextcloud integrations) — though "no runtime gate" is *inferred from absence of documentation*, and Spike 0 confirms it for free. **STRIKE the first draft's claim that `css_variables` "ships in CODE with no runtime check, posture-only."** Collabora's own theming docs/blog position `css_variables` explicitly *"if you are a Collabora partner or a customer running your own installation"* — i.e. partner/customer-positioned and **UNVERIFIED in stock CODE**; the CSS/theming assets are themselves proprietary/EULA-covered. We do not rely on it: colours come from **our own chrome in our own DOM**. Removing the Collabora logo/name touches proprietary branding + trademark — resolved cleanly only by a **self-built unbranded build from MPL-2.0 source** (which the custom-UI requirement aligns with anyway).

## Licensing & copyleft verdict (VERIFIED)

> **Central correction, stated once and loudly:** Collabora Online source is **MPL-2.0, not AGPLv3.** A 2022 community *suggestion* to switch CODE to AGPLv3 was **declined by Collabora** (it was not a formal governance proposal-and-rejection, and the year is **2022**, not 2023 as the first draft said). COOL `COPYING` is verbatim MPL-2.0. **There is no AGPL and no network copyleft anywhere in this stack.** The fork's `frontend-chrome` dossier called Collabora "AGPLv3" — that claim is **wrong**; do not propagate it into the ADR or NOTICES.

**Per-component reality (the "surface each license precisely" obligation — the stack is NOT mono-MPL):**

| Component | License | Copyleft | Net obligation |
|---|---|---|---|
| LibreOffice core / LOK (server-side) | **dual MPL-2.0 / LGPLv3+** | Weak / file-level (LGPL *is* copyleft — must be named) | Notice; we run it unmodified, don't distribute it standalone |
| **COOL / CODE source** | **MPL-2.0** (2022 AGPLv3 suggestion **declined**) | Weak / file-level | If we self-build & modify COOL files → publish *those files*; preserve notices; **no network copyleft, no app-wide taint** |
| COOL `browser/` subfolder | **BSD** | Permissive | Notice |
| Bundled fonts | **OFL-1.1** | Permissive (font-scope) | Notice |
| Dictionaries (Hunspell / Hyphen) | **MPL-1.1** | Weak / file-level | Notice; trim to needed locales |
| Third-party libs in tree | Apache-2.0 / Boost / MIT | Permissive | Notice |
| CODE **prebuilt binary / official image** | MPL source **+ proprietary executable-form EULA + proprietary Collabora trademark/CSS + "not for production" disclaimer + 10-doc/20-conn cap** | n/a (proprietary distribution conditions, not copyleft) | **The real gate is commercial/ops + proprietary-binary terms, not source copyleft** |
| zetajs / zetaoffice glue (WASM path only — rejected) | MIT | — | — |

**Net vs the PyMuPDF precedent.** This **source** stack is **strictly lighter** than the AGPL-3.0 row already accepted in `NOTICES.md:76` (PyMuPDF, "the **only** copyleft dependency," grandfathered, server-side-only). Same server-side-only boundary *shape*, but weak/file-level (and LGPL/permissive) instead of strong + network. We run COOL as a **separate, unmodified container — not linked into `api`/`web`/gateway** — so copyleft reach is contained to that container.

**Do we need a Collabora subscription to run? No — by license.** A subscription buys support / SLA / updates / branding-removal / cap-removal, **not** the legal right to run (Collabora staff: *"build, brand and support it yourself from the MPLv2 source"*). **But the free official image's 10-doc / 20-connection hard cap + "not for production" framing + proprietary binary EULA + proprietary trademark/CSS are real gates.**

**Decisive consequence the first draft buried:** **the clean-MPL, unbranded posture is achievable ONLY on the self-build-from-source path.** Vendoring the official image inherits the proprietary executable EULA, proprietary trademark/CSS, and the production-use disclaimer. So self-build is not *merely* cap-removal — it is the **precondition for the clean-license claim this document makes**.

- **Maintainer decision — DECIDED (2026-06-25): self-build COOL from MPL-2.0 source.** Chosen for the strict licence posture + custom UI + cap removal, accepting the cost of owning a build + security-update burden (a real SBOM/supply-chain surface). The rejected alternatives — (2) vendor the official image and record the proprietary-binary terms, (3) buy a subscription — are recorded for the ADR. *Spike 0 may use the prebuilt `collabora/code` image (engine behaviour is identical) to validate fidelity fast; the self-build is a Slice-1 production-posture task, not a prerequisite for the go/no-go.*
- **Related follow-up the maintainer flagged (2026-06-25): revisit / clean up the PyMuPDF AGPL-3.0 dependency** (`NOTICES.md:76` — today the *only* strong-copyleft dep, grandfathered server-side-only). If PyMuPDF is removed or replaced, the codebase would carry **zero AGPL and zero strong/network copyleft anywhere** — leaving only weak/file-level (MPL/LGPL) + permissive licences, of which the self-built Collabora is one. Tracked as its own backlog item (own slice + ADR), **not** part of this editor work — but it makes the editor's clean-MPL posture the *whole* picture rather than an exception.
- **NOTICES.md must gain a row, modeled on the PyMuPDF row:** *Component = Collabora Online (CODE) + LibreOffice core. License = **MPL-2.0 for COOL source; LibreOffice core dual MPL-2.0 / LGPLv3+; `browser/` BSD; fonts OFL-1.1; dictionaries MPL-1.1**; weak/file-level copyleft only, **NO AGPL, no network copyleft**. Posture = server-side-only, separate unmodified container; obliges = preserve notices + publish any modified COOL files + use our own brand if we strip Collabora marks. The official prebuilt CODE binary additionally carries a proprietary executable-form EULA + proprietary Collabora trademark/CSS + a "not for production" disclaimer — the MPL-clean + unbranded posture requires self-building from MPL-2.0 source. **NOT AGPL.** Lighter than the grandfathered PyMuPDF AGPL-3.0 row.*

*Note:* "production-grade; 100M+ pulls" is marketing-flavored and not independently verified — non-load-bearing, do not lean on it in the ADR.

## Track-changes & comment fidelity verdict (VERIFIED, with risks)

**Conditionally safe for a legal redline tool — on a pinned modern build, with empirical pre-build verification (Spike 0) and one config lockdown.** Plain `w:ins`/`w:del` + threaded comments round-trip reliably on current LibreOffice/Collabora. But the fork's Adeu loop is sensitive to author-string identity, and there are named, load-bearing risks.

**The make-or-break invariant: author-name attribution.** The fork distinguishes "ours" vs user/counterparty by **exact author-string equality** to `DEFAULT_AUTHOR = "LQ.AI Commercial counsel"` (`api/app/agents/redline_service.py:66`; `is_ours = author == our_author` at `api/app/agents/negotiation_service.py:252`, author captured from Adeu's OOXML read at ~`:213`/`:234`/`:242-244`). **There is no fuzzy match and no fallback — any mutation of the OOXML `w:author` byte-string silently flips `is_ours`.**

Mitigations (must-do, and verified empirically in Spike 0):

- Set WOPI `UserFriendlyName` to the lawyer's real name (distinct from `DEFAULT_AUTHOR`), **force track-changes ON** in the session.
- **`UserFriendlyName` → OOXML `w:author` byte-mapping is UNVERIFIED in vendor docs — keep this a hard go/no-go, not a footnote.** Collabora docs confirm only that each change carries *an* author/date and that `UserFriendlyName`/`UserId`/`UserExtraInfo` are the WOPI identity inputs — **none state which field byte-stamps `w:author`, nor that it round-trips verbatim.** Spike 0 must round-trip an Adeu redline, read it back through `read_state_of_play`, and assert `author ≠ DEFAULT_AUTHOR` *and* `is_ours` still works.
- **"Remove personal information on saving" must be OFF and enforced — promote to a TOP-3 risk (the first draft buried it).** Since LibreOffice **24.8**, `Tools ▸ Options ▸ Security ▸ Remove personal information on saving` **strips author names + timestamps from tracked changes on every save, including DOCX.** If on, it **wipes the exact `w:author` string `is_ours` compares against** → every prior agent change reads back as `unknown` → `is_ours=False` → the whole checklist/discriminator collapses **silently, with no error.** Assert OFF in coolwsd config *and* verify it in Spike 0's read-back; ideally enforce server-side.
- **Attribution is bidirectional — protect both sides.** New user edits must read as the *lawyer* (not the agent); AND the agent's pre-existing `w:author="LQ.AI Commercial counsel"` changes must **survive a Collabora save byte-for-byte** (if Collabora normalizes existing authorship, or the personal-info strip fires, the agent's own prior changes flip to `is_ours=False` and re-enter the checklist as if counterparty). Spike 0 asserts both.

**Other named risks:**

- **Tracked MOVES.** *Correction:* the first draft cited **tdf#145720** as "moves degrade to delete+insert" — that bug is a *years-old feature-completion* item (DOCX MoveTo/MoveFrom export, ~7.3 era), **stale/mis-cited**. The live move-fidelity risk is a different class (e.g. **tdf#149707** — moved list-item paragraph marks not exported correctly). Keep the move risk in the spike, **re-cited as tdf#149707 + verify-on-pinned-version**. The *consequence* still holds: a move that re-saves as two `Chg` spans shifts the `Cn` checklist refs (Adeu reads `Chg` ids per region).
- **Comment reply order — fixed, but it makes a modern build mandatory.** **tdf#160814** (replies with the same range inserted out of order) was **fixed in 24.8.0**. This touches C5b reply-threading (`parent_id`, `negotiation_service.py` ~`:251`) directly → pin **≥ 24.8** is load-bearing, not boilerplate.
- **Comment-on-tracked-change drift.** *Correction:* the first draft framed this as a "25.8 known issue" — that specific claim is **unsourced/UNVERIFIED**. It is *plausible* (it's exactly the silent-loss class the C5b `evaluate_anchoring` gate guards) → treat as a **hypothesis folded into the Spike 0 corpus**, not asserted as known behavior. The agent only re-reads after *its own* writes today, so a semantic drift from a user's editor save is caught only at hand-back re-read.
- **Adeu has never parsed Collabora-authored OOXML.** Adeu's round-trip is proven against Adeu-authored and Word-authored markup (C5a/C5b). **Collabora-authored `w:ins`/`w:del`/`w:comment` XML is a third dialect.** Spike 0 must run the read-back specifically through `read_state_of_play` (the Adeu parser, not just the LO engine, is the untested seam).
- **Comment-id stability.** C5b reply-survival matches on **raw** comment ids. If Collabora re-indexes `w:comment` ids on `PutFile`, reply-pairing/`parent_id` threading can scramble even when text survives. Add a comment-id-stability assertion to Spike 0.

**Required discipline:** pin one CODE / LibreOffice version, run the fork's existing C5a/C5b round-trip fidelity corpus against it before adoption, and re-run on every bump.

## Deployment & ops

- **One new stateless `collabora` (CODE) compose service.** Pinned version (≥ 24.8 for fidelity; ≥ 24.04.11.2 / current 25.04.x for `Hide_Command`). **Bound to loopback**, reachable only by `api` on the private compose network, **no gateway reachability**. Set the WOPI allow-list (`aliasgroup1`) to exactly the `api` origin. Resources: ~1.5–2 GB RAM per active document.
- **Reverse proxy — corrected.** *The first draft said "Caddy." There is **no Caddyfile in the repo**; the `web` service is a standalone SvelteKit SPA **served by nginx** on `:8080`, and the compose comments expect an **operator-supplied** reverse proxy for production.* The same-origin `/collabora/*` route + WebSocket upgrade + CSP must be designed against **nginx (or the operator's proxy)** — and **there is no in-repo proxy config to extend today**, so this is **net-new infra, not a one-line route add** (this understates Slice 1 if treated as trivial). Prefer **same-origin** (`/collabora/` under the existing web host) to simplify CSP/cookies and sidestep COOP/COEP.
- **CSP is greenfield.** Confirmed by grep: **no `frame-src` / `frame-ancestors` / CSP anywhere** in `api/`, `web/`, or compose today. Add `frame-src` + `connect-src` for the Collabora origin and `frame-ancestors` on coolwsd (`--o:net.content_security_policy`, ≥ 24.12.4.1). Security-review item.
- **Image size / disk.** The CODE image is large (several GB). On the Crostini/btrfs host that already hit 100%: **trim `dictionaries` to `en_GB en_US`**, and **`docker image prune -f` (dangling only)** after each version bump per CLAUDE.md. Never `prune -a`, never touch volumes/build cache, never `down -v`.
- **Security hardening.** Pin a build past CVE-2025-27791; origin allow-list; loopback bind; treat every `PutFile` body as untrusted (`guard_ooxml` + size cap); counts-only audit; **defer proof-key signing** (threat model rests on file-scoped short-TTL token + private network + allow-list).
- **Dev-stack fit.** New service = rebuild `api` (+ workers if a migration lands); rebuild the **prebuilt `web` bundle** before debugging the editor UI; Cypress light/dark for the cockpit tab.

## Risks & open questions

Ranked; each with how to resolve / the spike.

1. **`UserFriendlyName` → OOXML `w:author` byte-mapping is UNVERIFIED** *(highest — breaks the whole `is_ours` discriminator if wrong).* → **Spike 0:** round-trip an Adeu redline, read back via `read_state_of_play`, assert `author ≠ DEFAULT_AUTHOR` and `is_ours` still works, **both directions** (user edits attributed to lawyer AND agent's prior `DEFAULT_AUTHOR` changes preserved byte-for-byte). **Hard go/no-go.**
2. **"Remove personal information on saving" silently wipes authorship** *(silent total-loss).* → Assert OFF in coolwsd config + verify in Spike 0 read-back; enforce server-side if possible.
3. **CODE free-image gates: 10-doc/20-conn cap + "not for production" + proprietary binary EULA/trademark/CSS** *(blocks multi-user prod AND the clean-license posture).* → Maintainer decision in the ADR: **self-build from MPL source (recommended — only route to the clean/unbranded posture)** vs vendor-image-with-recorded-terms vs subscription.
4. **Track-change round-trip mutations on the pinned build** (moves → ref-shift; Collabora-authored OOXML as a third Adeu dialect; comment-id renumbering; comment-on-change drift). → Run the fork's C5a/C5b fidelity corpus + a comment-id-stability assertion through `read_state_of_play` in Spike 0; document/pin.
5. **Residual canvas chrome + `Hide_Command` reliability** (no `Hide_Toolbar`; #13224 "no effect" report). → Spike 0 proves the hide surface clears the intended buttons on the exact pinned build; otherwise cover/theme the residual strip.
6. **Concurrent user-edit vs live agent run** *(worse than "no lock" — the WOPI lock does NOT cover it, because Adeu and Collabora write to **different** new File rows; a hand-back can race a still-running agent write and re-read a stale version).* → **Primary control:** gate hand-back / open read-only while `runActive` (`ConversationHost.svelte` ~`:165`) is true. State this as the primary mechanism, not a backstop.
7. **No file-version lineage** — `files` has no `version`/`supersedes` column (confirmed at `api/app/models/file.py` ~`:33`); `PutFile` creates fresh rows. → Decide: add a nullable `supersedes_file_id` FK migration (cleaner "keep editing" loop, ADR-worthy, rebuild api+workers) vs re-bind the session to the new id after `PutFile`.
8. **No reverse-proxy config in the repo + no CSP today** — net-new nginx/operator-proxy `/collabora/` + WS + CSP infra. → Build it in Slice 1; same-origin to minimize CSP/cookie/COOP-COEP surface; security-review.
9. **`css_variables` is partner/customer-positioned + proprietary, UNVERIFIED in stock CODE.** → Do **not** rely on it; colours come from our own chrome. Confirm in the ADR; strike any "ships in CODE, no runtime check" language.
10. **Image bloat on Crostini/btrfs.** → Trim dictionaries; prune dangling only after each bump.
11. **Multi-pass nesting on an already-tracked document** *(VibeLegalStudio's central failure — re-redlining a `.docx` that already has tracked changes produced un-renderable nested `<w:ins><w:del>`).* The editor round-trip re-introduces this scenario: on hand-back the agent may redline over the lawyer's *and its own prior* changes. **Assessed — the fork LIKELY avoids it.** Unlike the prior project (which re-parsed marked-up XML and injected on top), the fork gates counters against the **clean accept-all text** (`commercial_tools.py:739-744`) and word-diffs against full document text via Adeu's `generate_edits_from_text` → `apply_edits` (`redline_service.py:182-192`, `negotiation_service.py:334-346`); `test_apply_decisions_full_round_reconciles` (`test_negotiation_service.py:84-115`) empirically applies a counter on an already-marked doc and re-reads it cleanly. **Residual unknown:** no test inspects the OOXML at the `w:ins`/`w:del` level to *prove* zero nesting, and it is unconfirmed whether `engine.mapper.full_text` returns clean vs marked text. → **Fold into Spike 0** (below). Materially lower risk than VibeLegalStudio faced — but confirm at the byte level before relying on it.

## Phased slice plan

Vertical, ~2–3 days each, one PR each.

- **Spike 0 (throwaway, NOT on the dev stack) — "the engine is safe."** On a throwaway container: open an Adeu-produced redlined `.docx` in pinned CODE; edit + comment + accept/reject + save-back; read back through `read_state_of_play`. **Proves:** `UserFriendlyName`→`w:author` mapping works and `is_ours` holds **both directions**; "remove personal info" is OFF and authorship survives; move/comment-drift/comment-id behavior is known; Collabora-authored OOXML parses through Adeu; `Hide_Command`/`Hide_Button` actually clear buttons on the pinned build; the hide/UNO surface is ungated in free CODE; **and — the multi-pass check (Risk #11) — after the editor round-trip, run the agent's redline once more on the saved (already-tracked) `.docx` and assert the OOXML has NO nested `<w:ins><w:del>` and `read_state_of_play` still parses it** (the failure that sank VibeLegalStudio's multi-pass; the fork's gate-against-clean-text design should avoid it, but prove it at the byte level here). **Decides go/no-go and pins the version.** *No shippable code.*
- **Slice 1 — "Collabora runs locally, isolated, and behind our proxy."** Add the `collabora` compose service (pinned, loopback bind, caps, dictionaries trimmed, allow-list = `api`, no gateway reachability), the **net-new nginx `/collabora/*` WS route + CSP** (no in-repo proxy exists), the `NOTICES.md` row, and the ADR draft. **Proves:** the service is up, sandboxed, same-origin, and licensing is recorded.
- **Slice 2 — "WOPI host serves bytes, authz'd."** Build `wopi.py` (CheckFileInfo + GetFile + Lock family) + `editor-session` mint + `_TYPE_WOPI` token, all on `_load_visible_file`, with the `file_id`-claim-equals-URL check. **Proves:** Collabora opens a file read-only with the three-layer cross-user-404 guarantee on existing storage/auth seams.
- **Slice 3 — "Save-back lands a new user-authored version."** `PutFile` → `guard_ooxml` → new `File` row (`created_by_run_id=None`) + counts-only audit; lock enforcement (409 + `X-WOPI-Lock`). **Proves:** edits persist with correct provenance and appear in the Documents tab.
- **Slice 4 — "Editor in the cockpit, our chrome."** `DocumentEditorPanel` + `DocumentEditorToolbar` + `collaboraBridge`; new `matterTab='editor'` with the no-remount pattern; hide/collapse chrome, drive via postMessage/UNO, theme push, "Open in editor" entry. Rebuild the `web` bundle; Cypress light/dark. **Proves:** the Vercel-chrome / their-canvas reskin and the editing UX.
- **Slice 5 — "Hand back, agent resumes."** Hand-back button → save → seeded composer → `POST /agents/runs` on the same `thread_id` (thread_id only); gate hand-back / read-only on `runActive`. **Proves:** the full loop — agent redline → lawyer edits → agent re-reads markup and continues — end-to-end, live.

## Proposed ADR

**ADR-FNNN — In-app Word editor via self-hosted Collabora Online over WOPI**
*Status: proposed*

**Context.** After the agent redlines a `.docx` (Adeu, native tracked changes/comments), the lawyer needs to view/edit/comment/export it in-app and let the agent resume reading their markup. Maintainer constraint: "only LibreOffice is acceptable," local/self-hosted, no SaaS; UI must match ADR-F013; strict no-copyleft-surprises posture; cross-user → 404; provider keys gateway-only; documents are untrusted input.

**Considered options.**
1. **Collabora Online / CODE, self-hosted, WOPI-integrated, reskinned** — LibreOffice-on-LOK; built-in tracked-changes/comment UI; **MPL-2.0 source** (core dual MPL/LGPLv3+), no AGPL.
2. **LibreOffice-WASM (ZetaOffice), client-side** — best *potential* reskin, but track-change round-trip **unverified**, ~250 MB–1 GB browser payload, ships MPL+LGPL to the client (heavier license, client distribution), mandates COOP/COEP.
3. **Custom LOK build** — total UI control, but reinvents Collabora as net-new C++; **identical licensing**, strictly more cost/risk/security ownership.

**Decision.** Adopt Option 1: a new stateless `collabora` (CODE) compose service, with `api` as the WOPI host on existing File/auth/storage seams, reskinned to ADR-F013 by hiding/collapsing built-in chrome and driving the canvas from our Svelte toolbar via postMessage/UNO. **Self-build from MPL-2.0 source** to remove the 10-doc/20-conn cap, strip Collabora branding, and reach the clean-license posture (**maintainer confirmed self-build, 2026-06-25**; vendor-image and subscription rejected). Empirical go/no-go gated on Spike 0 (author-attribution byte-mapping + round-trip fidelity + personal-info-strip OFF + hide-surface).

**Consequences.**
*(+)* Production-grade engine; real tracked-changes/comment fidelity; agent resumes via the existing C5a `extract_counterparty_position` path with **zero new agent code**; **lighter copyleft than the accepted PyMuPDF AGPL** (weak/file-level MPL-2.0 + LGPLv3+/BSD/OFL, server-side, separate unmodified container, **no AGPL, no network copyleft**).
*(−)* New SBOM/supply-chain + CVE-patch surface (pin + watch advisories; the **self-build** path is the precondition for the clean-license/unbranded claim and adds a build burden); large image (mitigate: trim dictionaries, prune dangling); **residual canvas chrome (toolbar strip, context menus, dialogs) cannot be deleted — covered/themed only**; author-attribution + round-trip fidelity are **UNVERIFIED until Spike 0** and the build must be pinned; **"Remove personal information on saving" must be enforced OFF** or the `is_ours` discriminator collapses silently; a new untrusted-frame data plane needs **net-new nginx proxy + CSP** (no in-repo proxy today) and 404-not-403 WOPI authz; possible `supersedes_file_id` migration for an in-place editing loop; concurrent agent-write vs user-edit is guarded by gating hand-back on `runActive` (the WOPI lock does **not** cover it).
*(license note)* NOTICES.md records **MPL-2.0 (+ LGPLv3+/BSD/OFL/MPL-1.1)** and the proprietary-binary caveat for the official image. **Not AGPL** — the `frontend-chrome` dossier's AGPL claim is incorrect.

## Sources

**Collabora / licensing**
- Collabora Online `COPYING` (MPL-2.0): https://github.com/CollaboraOnline/online/blob/master/COPYING
- Collabora Online MPLv2 terms (executable-form proprietary conditions): https://www.collaboraonline.com/terms/collabora-online-mplv2/
- LWN — "Switch to AGPLv3 for CODE?" (Dec 2022 suggestion, declined): https://lwn.net/Articles/916533/
- Collabora forum — CODE binary license (proprietary trademark/CSS, "not for production," build-it-yourself): https://forum.collaboraonline.com/t/code-binary-license/179
- Collabora CODE page: https://www.collaboraonline.com/code/
- Nextcloud community — 10 docs / 20 connections cap: https://help.nextcloud.com/t/collabora-document-limitation-by-purpose-10docs-20connections/4425
- LibreOffice licenses (MPL-2.0 / LGPLv3+): https://www.libreoffice.org/licenses/
- CVE-2025-27791 advisory (malicious-WOPI file write): https://github.com/CollaboraOnline/online/security/advisories/GHSA-9j32-gg3j-8w25

**WOPI / integration / reskin**
- Collabora SDK — How to integrate (WOPI iframe + access_token + postMessage flow): https://sdk.collaboraonline.com/docs/How_to_integrate.html
- Collabora SDK — PostMessage API (Hide_*, Send_UNO_Command, Action_Save/Export/Close, Disable_Default_UIAction; `Hide_Command` "New in 24.04.11.2"): https://sdk.collaboraonline.com/docs/postmessage_api.html
- Collabora SDK — Theming / `css_variables` ("partner or customer" positioning): https://sdk.collaboraonline.com/docs/theming.html
- Collabora blog — Theming of Collabora Online: https://www.collaboraonline.com/blog/theming-of-collabora-online/
- Collabora SDK — Configuration (no documented `UserFriendlyName`→`w:author` mapping): https://sdk.collaboraonline.com/docs/installation/Configuration.html
- GitHub issue #13224 — `Hide_Command` has no effect (25.04.6.1): https://github.com/CollaboraOnline/online/issues/13224
- Collabora forum — no `Hide_Toolbar`; full top-bar removal only via Tabbed-view collapse: https://forum.collaboraonline.com/t/disable-toolbar/1221
- Collabora forum — `Document_Loaded` timing; read-only docs never emit it: https://forum.collaboraonline.com/t/how-to-hide-menubar-and-statusbar-for-read-only-documents/3871
- GitHub issue #6995 — hide menubar in compact view: https://github.com/CollaboraOnline/online/issues/6995

**Track-changes / comment fidelity**
- LibreOffice 24.8 release — privacy features (Remove personal information on saving): https://blog.documentfoundation.org/blog/2024/08/22/libreoffice-248/
- ThreatsHub — LibreOffice removes personal data from documents: https://www.threatshub.org/blog/libreoffice-now-removes-personal-data-from-documents-why-that-matters/
- tdf#145720 — DOCX export: support MoveTo/MoveFrom (years-old feature item; mis-cited in first draft): https://bugs.documentfoundation.org/show_bug.cgi?id=145720
- tdf#149707 — change-tracking of a moved list item's paragraph mark not exported: https://www.mail-archive.com/libreoffice-bugs@lists.freedesktop.org/msg879055.html
- tdf#160814 — DOCX comment replies in wrong order (fixed 24.8.0): https://www.mail-archive.com/libreoffice-bugs@lists.freedesktop.org/msg1021678.html
- Collabora — How to track and manage changes (per-change author/timestamp): https://www.collaboraonline.com/blog/how-to-track-and-manage-changes-in-collabora-online/
- Collabora forum — track changes not preserved (0-byte/format root cause): https://forum.collaboraonline.com/t/track-changes-not-preserved-in-the-file/807
- LibreOffice 26.2.3 — DOCX round-trip fixes: https://linuxiac.com/libreoffice-26-2-3-released-with-more-than-40-bug-fixes/

**WASM (rejected path)**
- allotropia / zetajs (ZetaOffice modes; no confirmed zero-chrome standalone): https://github.com/allotropia/zetajs

**Local seams (canonical over external docs)**
- `api/app/api/files.py:507` — `_load_visible_file` cross-user-404 chokepoint
- `api/app/security/jwt.py:49,146,164` — `_TYPE_MFA` token pattern to model `_TYPE_WOPI`
- `api/app/agents/commercial_tools.py:54,92,223,484,508-526,586` — `guard_ooxml` import, `_MAX_DOCX_BYTES`, resume path, `_apply_redline` write
- `api/app/agents/negotiation_service.py:182,252` — `read_state_of_play`, `is_ours` author-equality
- `api/app/agents/redline_service.py:66` — `DEFAULT_AUTHOR`
- `api/app/pipeline/readers/_base.py:325` — `guard_ooxml` (NOT `agents/_base.py`)
- `api/app/storage.py:346,457` — `stream_download` / `upload_bytes`
- `api/app/api/agent_runs.py:166,268` — Redis stream bridge (connection only), `create_agent_run`
- `api/app/api/__init__.py:93,98,104` — bare router mount precedent (`word_addin.public_router`)
- `docker-compose.yml:365` — web served by **nginx** (no Caddy); reverse proxy is operator-supplied
- `NOTICES.md:76` — PyMuPDF AGPL-3.0 precedent row
