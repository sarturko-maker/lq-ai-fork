# Plan — LibreOffice editor **Slice 1**: local, isolated Collabora service behind our proxy (+ NOTICES + ADR-F047)

## Context

The maintainer wants an embedded Word editor: agent redlines a `.docx` → lawyer views/edits/comments/exports
in-app → hands back → agent resumes reading the markup. Research (`docs/fork/research/libreoffice-editor.md`)
chose **Collabora Online (LibreOffice) over WOPI, `api` as the WOPI host, reskinned via our Svelte chrome**, and
**Spike 0 returned GO** (`docs/fork/evidence/libreoffice-spike0/` — author byte-strings survive, comments survive,
zero multi-pass nesting, on Collabora Office 26.04.1.4). The 6-slice plan starts here.

**Slice 1 = "the engine is wired into our stack, isolated, licensed, and decided."** It stands up Collabora as a
new local docker service reachable only through our web proxy (same-origin), adds the minimal framing CSP, records
the licence posture in `NOTICES.md`, and lands the architecture ADR. **No application code** (no api/web TS, no
migration, no dependency) — that is Slice 2 (WOPI host) onward. Runnable, verifiable infra+docs vertical.

## Posture decision (resolved by research — `collabora/code` prebuilt, clean build deferred)

The maintainer was hesitant about a from-source build; research (3 verification passes, primary sources) settled it:
- **The cap is gone** in current CODE (performance-based, not a hard 10-doc/20-conn limit).
- **"Not for production" is a support/warranty framing, not a licence prohibition** — the MPL-2.0 source has no
  production restriction; the subscription requirement targets the *branded supported* product. Internal,
  self-hosted, non-redistributed use of the prebuilt `collabora/code` is legally defensible (and ubiquitous).
- **We wrap it in our own chrome** (canvas-only + our Svelte toolbar); CSS theming of residual chrome is officially
  permitted for self-hosted installs → low branding/trademark exposure without touching the binary.
- The **only** thing a 30 GB from-source build buys is a zero-gray-zone unbranded image + immunity from Collabora's
  "subscribe at scale" intent — neither needed to build/validate/internally-run the editor.

**Decision: use the pinned prebuilt `collabora/code` image for the dev stack and all integration slices.** The
clean-posture choice — **from-source build OR a Collabora subscription** — is recorded as a *productionization*
decision (tracked in the ADR + MILESTONES), NOT a near-term committed slice. No 30 GB build now.

## Files & changes

### 1. `docker-compose.yml` — add a `collabora` service (no host port = strongest isolation)
- `image: collabora/code@sha256:<digest>` — pin by **digest** of the Spike-0-validated 26.04.1.4 (resolve via
  `docker inspect`), with a human-readable tag in a comment. (≥24.8 fidelity + ≥24.04.11.2 `Hide_Command` satisfied.)
- **No `ports:`** — reachable only over `lq-ai_default` by `web` (the proxy) and able to reach `api` (WOPI
  callbacks, Slice 2). Not exposed to host/loopback → not publicly reachable; admin console unreachable.
- `cap_add: [MKNOD]` (Collabora's sandbox needs it); **no `privileged: true`**. If the mount-namespace sandbox
  needs more on this host, prefer `extra_params: --o:mount_namespaces=false` over granting `SYS_ADMIN` — decide
  empirically at bring-up and record what was actually needed.
- `environment`:
  - `aliasgroup1=http://api:8000` — WOPI host allow-list (anticipates Slice 2; harmless now).
  - sub-path reverse-proxy config so Collabora serves correctly under `/collabora/` (coolwsd
    `--o:net.proxy_prefix=true` / `service_root` per Collabora's documented nginx sub-path setup) +
    `--o:net.frame_ancestors=<our web origin>` (so Collabora permits being framed by us) +
    `--o:net.content_security_policy` consistent with the nginx CSP.
  - `extra_params=--o:ssl.enable=false --o:ssl.termination=true` (TLS at the operator proxy in prod; none in dev).
  - `dictionaries=en_GB en_US` (trim — disk discipline), `DONT_GEN_SSL_CERT=true`, admin `username`/`password`
    from env (console stays unreachable; creds only so coolwsd doesn't default-open).
- `healthcheck`: `curl -f http://localhost:9980/hosting/discovery`.
- `restart`, `depends_on: api`, joins the default network implicitly.
- `.env.example`: add `COLLABORA_ADMIN_USER` / `COLLABORA_ADMIN_PASSWORD` (dev defaults; **never** real secrets).

### 2. `web/nginx.conf` — same-origin `/collabora/` proxy + minimal framing CSP
- Add `location /collabora/ { proxy_pass http://collabora:9980/; … }` with WebSocket-upgrade headers
  (`Upgrade`/`Connection "upgrade"`, `Host`, `X-Forwarded-*`) and the proxy-prefix header coolwsd expects for
  sub-path hosting. Mirror the file's **explicit-add_header rule** (a `location` with any `add_header` inherits
  none — declare the full set per block; `web/nginx.conf:7-9`).
- **CSP kept deliberately narrow** (greenfield; a full `script-src`/`style-src` CSP is its own hardening project and
  risks breaking the SPA). Add only the **framing** directives — they don't affect script/style loading — on
  `location /` and `/collabora/`: `add_header Content-Security-Policy "frame-src 'self'; frame-ancestors 'self'";`
  (same-origin ⇒ `'self'` covers the editor). Fuller CSP noted as future hardening, not this slice.
- Validate with `nginx -t` in the built `web` image.

### 3. `NOTICES.md` — add a Collabora/LibreOffice row (mirror the PyMuPDF posture)
- New row/section in the existing table format (`NOTICES.md:20-36`), modelled on the PyMuPDF precedent:
  Component = **Collabora Online (CODE) + LibreOffice core**; License = **MPL-2.0 (COOL source); LibreOffice core
  dual MPL-2.0 / LGPLv3+; `browser/` BSD; fonts OFL-1.1; dictionaries MPL-1.1 — weak/file-level only, NO AGPL, no
  network copyleft**; Posture = **server-side-only, separate UNMODIFIED prebuilt container** (WOPI host in `api`,
  iframe in `web`, no client-side egress). Note honestly: the dev stack runs the **prebuilt official CODE binary**
  (MPL-2.0 source under a proprietary executable-form EULA + Collabora trademark/CSS; "not recommended for
  production" = unsupported, **not** a licence prohibition; the historical 10-doc/20-conn cap is **removed** in
  current CODE). Record that the **clean unbranded / supported production posture is a deferred choice —
  self-build from MPL-2.0 source OR a Collabora subscription — decided at productionisation.** **Lighter than the
  grandfathered PyMuPDF AGPL-3.0 row. NOT AGPL.** `LICENSE` (Apache-2.0) untouched.

### 4. `docs/adr/F047-collabora-online-editor.md` — the architecture ADR (status: proposed)
- MADR-minimal (mirror `F046`): Context (product goal + Spike-0 GO + constraints) · Considered options
  (Collabora/WOPI · LibreOffice-WASM · custom-LOK — from the research doc) · Decision outcome (Collabora/CODE over
  WOPI, `api` host, **prebuilt image now**, reskin via our Svelte chrome) · Consequences (licence posture vs
  PyMuPDF; the **deferred build-or-subscribe productionisation decision** with its trigger = real production scale;
  residual canvas chrome; the deferred WOPI-host slices; CSP greenfield). References the research doc + Spike-0
  evidence.

### 5. Docs housekeeping
- `docs/fork/MILESTONES.md`: add the LibreOffice-editor milestone with the 6 slices (S1 = this) + a
  productionisation backlog line (build-or-subscribe) + the existing PyMuPDF-AGPL-cleanup backlog line.
- `docs/fork/HANDOFF.md`: overwrite the pickup marker → "Editor Slice 1 shipped; pick up Slice 2 = WOPI host".
- `docs/fork/plans/LIBREOFFICE-EDITOR-slice1.md`: commit this plan (fork convention).

## Non-goals (explicitly later slices)
- WOPI host endpoints + file-scoped token + cross-user-404 (Slice 2). No `api/app/api/wopi.py` yet.
- Save-back / new File version (Slice 3). Cockpit editor panel + reskin/postMessage (Slice 4). Hand-back / agent
  resume (Slice 5).
- The from-source unbranded image / subscription (deferred productionisation decision). A full
  script-src/style-src CSP (future hardening). PyMuPDF AGPL removal (separate slice + ADR).

## Verification (DoD — shown, not asserted)
1. **Build + start, isolated:** rebuild `web` (nginx.conf change) + `docker compose up -d collabora`; `docker image
   prune -f` (dangling only). Show `collabora` healthy (`/hosting/discovery` via its healthcheck). **Never**
   `down -v`.
2. **Same-origin route works:** `curl -fsS http://127.0.0.1:<web port>/collabora/hosting/discovery` returns the
   Collabora discovery XML **through the web proxy** (proves the sub-path proxy + WS-capable route). If sub-path
   hosting is fiddly, document the exact coolwsd flags that made it work (or the fallback) in the PR.
3. **Isolation proof:** show `collabora` has no host port (`docker compose port collabora 9980` → none) and the
   admin console is unreachable from host.
4. **CSP present:** `curl -I` the SPA + `/collabora/`; show `Content-Security-Policy: frame-src 'self';
   frame-ancestors 'self'`; `nginx -t` clean.
5. **Web suite green:** `cd web && npm run check && npm run test:frontend` (no TS touched — proves no regression);
   quote counts. (No api suite / migration — Slice 1 touches no app code.)
6. **Licence + ADR:** NOTICES row present; ADR-F047 drafted; `LICENSE` unchanged.
7. Fresh-context adversarial + **security + simplification** pass (every slice): new attack surface —
   untrusted-document engine isolation (no host port, MKNOD-only, allow-list = `api`), CSP correctness, no secrets
   in compose/env/NOTICES, admin console unreachable. Update HANDOFF; squash-merge under the ADR-F005 gate.

## Recommended order
compose `collabora` service → bring it up + iterate sub-path/sandbox flags until `/hosting/discovery` is healthy →
nginx `/collabora/` + CSP (rebuild web, prove same-origin discovery) → NOTICES row → ADR-F047 →
MILESTONES/HANDOFF/plan → verify → review → merge.
