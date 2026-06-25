# F047 — In-app Word editor via self-hosted Collabora Online over WOPI

- Status: proposed
- Date: 2026-06-25
- Deciders: maintainer (Arturs), agent
- Slice: libreoffice-editor Slice 1 (first of 6; the WOPI host + UI land in Slices 2–5)

## Context

The commercial agent's primary work product is a redlined `.docx` with native tracked changes
+ comments (C4/C8/C9, ADR-F031/F041/F045). Today the lawyer can only **download** it (C7a,
ADR-F046). The maintainer wants an **embedded editor**: agent redlines → the lawyer
views/edits/comments/exports the document **inside the tool** → hands it back so the agent
**resumes reading their markup** and continues negotiating. The agent already reads tracked
changes + comments (C5a/C5b: `extract_counterparty_position` / `respond_to_counterparty`), so
**no new agent capability is needed** — the editor is the missing UI.

Hard constraints (from CLAUDE.md + the maintainer): "only LibreOffice is acceptable", **local /
self-hosted, no SaaS**; the UI must match our Vercel design system (ADR-F013); strict
copyleft/licence posture (PyMuPDF's AGPL is the single grandfathered copyleft dep — no new
copyleft surprises); cross-user access → 404 not 403; provider keys live only in the gateway and
**every** LLM call routes through it (ADR-F010); retrieved/edited documents are untrusted input.

This decision is backed by a full research pass (`docs/fork/research/libreoffice-editor.md` — 9
research agents + 4 adversarial verifiers) and a throwaway **Spike 0** that returned **GO**
(`docs/fork/evidence/libreoffice-spike0/`): on the real engine (Collabora Office 26.04.1.4),
author `w:author` byte-strings survive a save verbatim (so the agent's `is_ours` discriminator
holds), the "remove personal info on save" strip is OFF by default, comments + multi-author
changes survive, there is **zero `<w:ins><w:del>` nesting even on the multi-pass case** (the
failure that sank the maintainer's earlier VibeLegalStudio project — our gate-against-clean-text
+ word-diff avoids it), and Adeu re-reads Collabora-serialised OOXML cleanly.

## Considered options

1. **Collabora Online / CODE, self-hosted, integrated over WOPI, reskinned via our Svelte chrome.**
   Collabora Online *is* LibreOffice running headless on LibreOfficeKit — it satisfies
   "only LibreOffice, local, no SaaS" and ships, already built, the per-document sandboxed engine,
   the tile protocol, the JS canvas client, and — decisively for a redline tool — the
   **tracked-changes + comment UI** that round-trips Word markup through the same LibreOffice core
   Adeu targets. Source is **MPL-2.0** (core dual MPL-2.0 / LGPLv3+), no AGPL.
2. **LibreOffice-WASM (ZetaOffice), fully client-side.** Best *potential* reskin, but the
   track-change round-trip is **unverified** in WASM, it ships a ~250 MB–1 GB MPL+LGPL payload to
   the browser (turning our clean server-side boundary into client distribution), and it mandates
   invasive COOP/COEP isolation of the web app.
3. **Custom build directly on LibreOfficeKit (LOK).** Total UI control, but reinvents Collabora
   (the WSD/ForKit/Kit/tile-cache/JS-client/comment-UI) as net-new C++ for **identical** licensing
   and strictly more cost, risk, and security-ownership.

## Decision outcome

**Chosen: option 1 — Collabora Online over WOPI, `api` as the WOPI host, reskinned via our Svelte
chrome.** This ADR governs the architecture; Slice 1 lands only the engine + its isolation +
licence record (the WOPI host, save-back, cockpit editor/reskin, and hand-back/resume are
Slices 2–5).

Slice 1 specifics:
- A new **`collabora` compose service** (Collabora Online / CODE), pinned **by digest** to the
  Spike-0-validated build, with **no host port** — reachable only over the private
  `lq-ai_default` network by `web` (the same-origin proxy) and able to reach `api` (the WOPI host,
  Slice 2). Sandbox uses `cap_add: [MKNOD]` only (no `privileged`/`SYS_ADMIN`). The WOPI host
  allow-list (`aliasgroup1`) is fixed to the `api` origin. **No gateway reachability** — the editor
  data plane never calls an LLM, so the ADR-F010 egress invariant is untouched.
- **Same-origin** hosting: the `web` nginx proxies `/collabora/` to the service (WebSocket-upgrade),
  **stripping the prefix** so coolwsd routes at its own root — the editor is served from our own
  origin, simplifying CSP and avoiding cross-origin/COOP-COEP. (Empirically, coolwsd **400s on a
  prefixed path** and `--o:net.proxy_prefix` does not change that, so the prefix is stripped at
  nginx; making coolwsd EMIT `/collabora/`-prefixed asset URLs for the iframe is a **Slice-4** task —
  proxy-prefix done right, a `<base>` tag, or a dedicated origin. The admin console is additionally
  hard-404'd at the proxy as defence-in-depth.) A **minimal framing CSP** (`frame-src 'self';
  frame-ancestors 'self'`) is added (CSP is greenfield here); a full `script-src`/`style-src` CSP
  is future hardening.
- **Build posture: the prebuilt `collabora/code` image is used for the dev stack and all
  integration slices.** Research settled the licence question: the cap is gone in current CODE,
  "not for production" is a support/warranty framing (not a licence prohibition), internal
  self-hosted non-redistributed use is defensible, and we hide Collabora chrome via our own UI +
  CSS (officially permitted for self-hosted installs). The clean unbranded / supported
  **production** posture — **self-build from MPL-2.0 source OR a Collabora subscription** — is a
  **deferred decision**, triggered at real productionisation (recorded in `docs/fork/MILESTONES.md`).
  Engine behaviour is identical between prebuilt and self-built, so deferring it blocks nothing.

## Consequences

- **(+)** A production-grade engine with real tracked-changes/comment fidelity; the agent resumes
  through the existing C5a path with **zero new agent code**; copyleft is **weak/file-level MPL-2.0
  (+ LGPLv3+/BSD/OFL/MPL-1.1), server-side, in a separate unmodified container — no AGPL, no
  network copyleft** — strictly **lighter than the accepted PyMuPDF AGPL** (NOTICES.md).
- **(+)** Strong isolation by construction: no host port, MKNOD-only, WOPI allow-list = `api`,
  admin console unreachable, untrusted documents confined to the sandboxed container.
- **(−)** A new SBOM / CVE-patch surface (pin by digest; re-pin + re-run the Spike-0 fidelity
  corpus on every bump). The **clean unbranded/supported production posture is deferred** (build or
  subscribe) — it must be decided before any real deployment, not before internal use.
- **(−)** Residual in-canvas chrome (context menus, dialogs, a thin toolbar strip) is
  LibreOffice-rendered and can be covered/themed but not deleted — accepted as the cost of a real
  engine (Slice 4 reskin).
- **(deferred)** The WOPI host endpoints + file-scoped token + cross-user-404 (Slice 2), save-back
  as a new user-authored `File` version (Slice 3), the cockpit editor panel + reskin/postMessage
  (Slice 4), and hand-back → agent resume (Slice 5) get their own slices; any architectural calls
  there extend or supersede this ADR.
- This ADR takes the next free fork number after **F046**; the WASM and custom-LOK paths are
  recorded as rejected so a future reader does not re-litigate them.

## Addendum — Slice 2: the WOPI host (2026-06-25)

Slice 2 implemented the WOPI **read** half (`api/app/api/wopi.py`): `CheckFileInfo`, `GetFile`, and
the **Lock family** (LOCK / GET_LOCK / REFRESH_LOCK / UNLOCK / UNLOCK_AND_RELOCK). These calls
materialise this ADR's "WOPI host endpoints + file-scoped token + cross-user-404" deferral. The
architectural calls made within that envelope (recorded here rather than minting a new ADR — F047
governs the editor):

- **Read-only viewer this slice.** `CheckFileInfo` advertises `UserCanWrite=false` / `ReadOnly=true`
  and omits `SupportsUpdate`, so the lawyer SEES the agent's redline with **no save path** — no
  data-loss window. Slice 3 flips to editable and adds `PutFile` atomically. (Milestone sequence:
  WOPI read → save-back.)
- **File-scoped editor token = a stateless signed JWT** (`create_wopi_token`, `typ="wopi"`), HS256
  on the existing `jwt_secret`, claims `sub`/`fid`/`name`/`exp`. No server-side session table.
  Three-layer authz: mint is gated by `ActiveUser` + `_load_visible_file` (cross-user → 404); the
  `fid` claim must equal the URL `{file_id}` (no cross-file replay); every WOPI handler re-runs
  `_load_visible_file(db, fid, claims.user_id)`. Token failure → **401**; file not visible → **404**.
  The router is mounted WITHOUT the user-bearer gate (same posture as `word_addin.public_router`).
- **Locks = a small `editor_locks` table** (migration `0074`, PK `file_id`, FK→files `CASCADE`,
  30-min TTL; expired ⇒ treated as unlocked). The WOPI lock state machine is a **pure function**
  (`app/schemas/wopi.decide_lock`) the handler wires DB I/O around — fully unit-tested incl. the
  409 + `X-WOPI-Lock`-echo / empty-string-when-unlocked semantics. `SupportsExtendedLockLength=true`
  → lock ids up to 1024 chars (`Text`). Implemented this slice (HANDOFF-recorded Slice-2 scope,
  de-risks Slice 3); a read-only session won't drive them live, so they're proven by unit tests + a
  curl smoke replicating Collabora's exact lock sequence.
- **`Version`/`X-WOPI-ItemVersion` = `File.hash_sha256`** (content-addressed); `OwnerId`/`UserId` =
  `uuid.hex` (WOPI requires **alphanumeric** — the hyphenated form is invalid).
- **No model calls; the host never reaches the gateway** (ADR-F010 trivially intact). Proof-key
  (`X-WOPI-Proof`) validation stays **deferred** — the threat model is the file-scoped short-TTL
  token + the private compose network + the `aliasgroup1` allow-list. New settings:
  `collabora_wopi_host` (WOPISrc base = `http://api:8000`), `wopi_token_ttl_seconds`,
  `collabora_post_message_origin`. No `docker-compose.yml`/nginx change (WOPI is server-to-server
  on the compose network).

## Addendum — Slice 3: PutFile save-back (2026-06-25)

Slice 3 made the session **editable** and added WOPI `PutFile`
(`POST /wopi/files/{id}/contents`, `X-WOPI-Override: PUT`) so the lawyer's edits in Collabora save
back. `CheckFileInfo` now advertises `UserCanWrite=true` / `SupportsUpdate=true` / `ReadOnly=false`
(`PutRelativeFile`/`RenameFile` stay disabled via `UserCanNotWriteRelative`). The architectural call
the kickoff flagged — **the version model** — was decided by the maintainer:

- **Version model = snapshot-then-mutate** (chosen over mutate-in-place-no-history and the rejected
  new-row-only, which would leave the editor's `WOPISrc` serving stale bytes on reload). WOPI requires
  the **row id** in the `WOPISrc` URL to keep serving the latest bytes; the **storage key** is
  internal, so we keep the ADR-0005 `key == row id` convention for *both* rows. On the **first** human
  save of an agent redline (`created_by_run_id` set), the agent's current bytes are **copied to a new
  immutable `File` row** (key `str(snapshot_id)`, provenance `created_by_run_id` carried over, name
  `… (agent draft).docx` → visible in the C7a Documents tab) **before** the live object is overwritten;
  the live row keeps its id, is mutated in place (new `hash`/`size`/`updated_at`), and flips to
  `created_by_run_id = NULL` (human-authored). Later saves just mutate in place (no per-autosave
  snapshot). A no-op autosave (identical hash) writes nothing and does not flip provenance. **Why:**
  the editor stays coherent across reloads AND the agent's work product is preserved as a recoverable
  prior version — the data-loss risk a plain mutate-in-place carries for legal work.
- **Data-safety ordering.** Copy-first is the invariant: the old bytes exist at the snapshot key
  before the live object is overwritten, so no crash loses them. Storage and DB are not one
  transaction; on a pre-overwrite failure the snapshot orphan is best-effort deleted (live bytes
  intact), and on a post-overwrite/commit failure the snapshot orphan is **kept** (it is then the sole
  copy of the redline — GC-recoverable; Collabora retries PutFile and converges).
- **`files.updated_at`** (migration `0075`, nullable, additive) is the in-place save's last-modified
  stamp. PutFile is the only path that mutates bytes in place (every other path creates a new row), so
  `LastModifiedTime = updated_at or created_at` is now honest, and the **`X-COOL-WOPI-Timestamp`
  save-race backstop** (→ `409 {"COOLStatusCode": 1010}` when the stored file changed since the editor
  loaded it) is meaningful. PutFile's JSON response carries the new `LastModifiedTime` (the documented
  Collabora quirk).
- **Untrusted upload surface.** The PutFile body is browser-supplied bytes → a size cap
  (`lq_ai_max_upload_size_mb`, streamed → 413), the existing `guard_ooxml` (zip-bomb / XXE → 400), and
  a `ooxml_subtype == "docx"` check (reject a renamed `.xlsx`/`.pptx` → 400) gate every save. Lock
  enforcement reuses a pure `decide_putfile_lock` (held-lock mismatch → 409 + `X-WOPI-Lock` echo;
  unlocked or matching → proceed). Counts-only audit `editor.file_saved`. No model calls; no migration
  beyond `0075`; no new dependency (`copy_object` added to `app/storage.py`). Re-ingestion of edited
  content (RAG re-index) and a view/edit session toggle are out of scope (backlog); the agent-resume
  loop reads the `.docx` bytes directly (Adeu), so it is unaffected.
