# Backend Phase E — Release Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make M1 actually shippable as a self-hosted product per PRD §1.3 and §7.5 — author the release CI pipeline, generate SBOM + SLSA provenance + keyless cosign signatures, ship a Helm chart, and complete the M1 security-doc deliverables enumerated in `docs/security/README.md`.

**Architecture:** Phase E is orthogonal to feature work. It touches only `.github/workflows/` (created from scratch — no CI exists yet), `deploy/helm/lq-ai/` (created from scratch), `docs/security/`, `docs/compliance/` (referenced, scope-bounded below), root markdown (`SECURITY.md`, `README.md`), and adds a couple of `Makefile` targets for local SBOM/lint convenience. Release workflow triggers on a git tag matching `v*.*.*` (and `workflow_dispatch` for dry-runs). All container signing uses sigstore keyless OIDC + Fulcio — no private-key custody — per the `cosign verify` example already documented in `docs/security/README.md`. Helm chart ships in-repo only (operators `git clone + helm install`); no chart registry distribution this cycle. Threat model is STRIDE-by-component summary depth (one table; references PRD §5 + ADR 0009 for design intent).

**Tech Stack:** GitHub Actions, `docker/build-push-action`, `anchore/sbom-action` (Syft → SPDX JSON), `actions/attest-build-provenance` (SLSA L3), `sigstore/cosign-installer` + `cosign sign --yes` keyless, Helm 3 (chart authored against k8s 1.27+), Markdown for docs. Container registry is `ghcr.io/legalquants/lq-ai-{api,gateway,web}`.

**Decisions made before this plan (anchor for the implementer):**

1. **Cosign custody = keyless OIDC + Fulcio.** `docs/security/README.md` already publishes the verify example using `--certificate-oidc-issuer https://token.actions.githubusercontent.com`. No `secrets.COSIGN_PRIVATE_KEY` plumbing. Operators forking the project who want operator-controlled keys swap that in themselves; that's a doc note, not Phase E work.
2. **Helm distribution = in-repo only.** Chart lives at `deploy/helm/lq-ai/`. Operators clone the repo and `helm install ./deploy/helm/lq-ai`. No OCI artifact push, no GitHub Pages Helm repo this cycle.
3. **Threat-model depth = STRIDE-by-component summary table.** Five rows (api / gateway / web / postgres / minio), STRIDE columns, named threats + named mitigations, cross-references to PRD §5 + ADR 0009. ~1-2 pages. Asset-Threat-Mitigation lens deferred.
4. **Scope = handoff's 5 workstreams + 3 extra M1 docs from `docs/security/README.md`.** The extra docs are `dependencies.md`, `cryptography.md`, `audit-logging.md` — each is an M1 deliverable per that contract table.
5. **Compliance Alignment Pack at `docs/compliance/` is OUT OF SCOPE for Phase E.** `docs/security/README.md` references it but treats it as a separate effort. Don't fold it in.

**Out of scope (do not extend Phase E to cover these):**
- Wave D (Knowledge browser, KB-to-matter loop, outputs panel, Saved Prompts surface, Receipts mode, Citation Engine UI).
- Wave F (the 5 V2-FALLBACK cleanup items from Wave B v2).
- Wave E sandbox onboarding (`matters.is_sandbox`).
- PR CI (test/lint/typecheck on every PR). Phase E ships the **release** workflow; a PR-validation workflow is a separate concern.
- Tagging and publishing an actual release. The pipeline must be ready; tag-and-publish is Kevin's call.
- Compliance Alignment Pack content (SOC 2 / ISO 27001 / ISO 42001 / GDPR / HIPAA / FedRAMP control mappings).
- Network access controls doc (`network-access-controls.md` is M2 per the README).

**Conventions (carry through every commit):**
- Conventional Commits: `feat(ci):` / `feat(deploy):` / `feat(docs):` / `docs(security):` / `chore(release):` / `test(ci):`.
- DCO sign-off mandatory: `git commit -s`.
- Co-author trailer in every commit body: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Verify after each commit: `git log -1 --format=fuller` shows `Signed-off-by:` + `Co-Authored-By:`.
- Push every commit (atomic commits → atomic pushes).

---

## File Structure

**New directories created by Phase E:**

```
.github/workflows/        # new — release.yml
deploy/                   # new
  helm/
    lq-ai/                # new — entire Helm chart
      Chart.yaml
      values.yaml
      values-example.yaml
      NOTES.txt
      .helmignore
      templates/
        _helpers.tpl
        configmap-gateway.yaml
        deployment-api.yaml
        deployment-gateway.yaml
        deployment-web.yaml
        deployment-postgres.yaml      # StatefulSet actually
        deployment-redis.yaml         # StatefulSet
        deployment-minio.yaml         # StatefulSet
        service-*.yaml                # one per service
        ingress.yaml
        secret-refs.yaml
        serviceaccount.yaml
```

**New files in existing directories:**

```
docs/security/
  threat-model.md         # new — STRIDE-by-component
  dependencies.md         # new — dep review + vuln monitoring
  cryptography.md         # new — primitives + key lifecycle
  audit-logging.md        # new — what's logged + retention
  releases/
    README.md             # new — cosign verify walkthrough
```

**Existing files modified:**

- `Makefile` — add `sbom`, `helm-lint`, `helm-template`, `release-dryrun` targets
- `SECURITY.md` — fix the `[URL TBD — published before v1 release]` GPG placeholder
- `README.md` — add SLSA Level 3 badge + link to `docs/security/`
- `docs/security/README.md` — add status flips for the new docs (M1 → Landed)
- `docs/PRD.md` — note Phase E completion in the §9 status table if such a table exists; otherwise skip
- `docs/M1-PROGRESS.md` — add Phase E line if the file tracks backend phases this way (verify before editing)

---

## Task ordering rationale

Foundation first, then supply-chain pipeline (each task adds to `release.yml`), then Helm (orthogonal but heavy), then docs. The pipeline tasks are sequential because each adds a step to the same workflow. Docs can technically parallelize but we keep them sequential for clean atomic commits.

1. **T0** — Scaffold release workflow + container builds (foundation)
2. **T1** — SBOM generation (Syft, SPDX JSON)
3. **T2** — SLSA build provenance attestation
4. **T3** — Cosign keyless signing of images + SBOM + provenance
5. **T4** — Helm chart authoring
6. **T5** — `threat-model.md` (STRIDE-by-component)
7. **T6** — `cryptography.md`
8. **T7** — `audit-logging.md`
9. **T8** — `dependencies.md`
10. **T9** — `docs/security/releases/README.md` (cosign verify walkthrough)
11. **T10** — `SECURITY.md` GPG-URL fix + `README.md` SLSA badge + `docs/security/README.md` status table flip
12. **T11** — Final verification: dry-run the release workflow on `workflow_dispatch`

---

## Task 0: Scaffold release workflow + container image builds

**Files:**
- Create: `.github/workflows/release.yml`
- Create: `Makefile` targets (append to existing `Makefile`)
- Modify: none yet (the workflow only RUNS on tag push, so committing it is safe)

**Background the implementer needs:**
The workflow triggers on `push` of a tag matching `v*.*.*` and on `workflow_dispatch` (for dry-runs). It builds three container images (api / gateway / web), tags them with the git tag, and pushes to `ghcr.io/legalquants/lq-ai-{api,gateway,web}`. Subsequent tasks (T1-T3) add SBOM / SLSA / cosign steps to this same workflow. T0's deliverable is a working build+push that we can re-run idempotently.

The api, gateway, and web subdirectories each have their own Dockerfile (verified: `api/Dockerfile`, `gateway/Dockerfile`, `web/Dockerfile`). Build context for each is the subdirectory.

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - "v*.*.*"
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Dry-run: build but do not push or sign"
        type: boolean
        default: true

permissions:
  contents: read
  packages: write
  id-token: write       # required for sigstore keyless signing (T3) + SLSA attestations (T2)
  attestations: write   # required for actions/attest-build-provenance (T2)

env:
  REGISTRY: ghcr.io
  IMAGE_OWNER: legalquants

jobs:
  build-and-push:
    name: Build ${{ matrix.service }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - service: api
            context: ./api
          - service: gateway
            context: ./gateway
          - service: web
            context: ./web
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Resolve image tag
        id: tag
        run: |
          if [[ "${GITHUB_REF}" == refs/tags/v* ]]; then
            echo "tag=${GITHUB_REF#refs/tags/}" >> "$GITHUB_OUTPUT"
          else
            echo "tag=dryrun-${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
          fi

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GHCR
        if: ${{ github.event_name == 'push' || !inputs.dry_run }}
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        id: build
        uses: docker/build-push-action@v5
        with:
          context: ${{ matrix.context }}
          push: ${{ github.event_name == 'push' || !inputs.dry_run }}
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_OWNER }}/lq-ai-${{ matrix.service }}:${{ steps.tag.outputs.tag }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_OWNER }}/lq-ai-${{ matrix.service }}:latest
          provenance: false   # we attach SLSA provenance via actions/attest-build-provenance in T2
          sbom: false         # we attach SBOM via anchore/sbom-action in T1
```

- [ ] **Step 2: Add Makefile convenience targets**

Append to `Makefile`:

```makefile
# ----------------------------------------------------------------------
# Release-readiness (Phase E)
# ----------------------------------------------------------------------

.PHONY: release-dryrun
release-dryrun:
	@echo "Trigger the release workflow on workflow_dispatch with dry_run=true to test locally."
	@echo "gh workflow run release.yml -f dry_run=true"

.PHONY: helm-lint
helm-lint:
	helm lint deploy/helm/lq-ai

.PHONY: helm-template
helm-template:
	helm template lq-ai deploy/helm/lq-ai \
		--values deploy/helm/lq-ai/values-example.yaml

.PHONY: sbom
sbom:
	@mkdir -p artifacts/sbom
	syft scan dir:./api -o spdx-json=artifacts/sbom/api.spdx.json
	syft scan dir:./gateway -o spdx-json=artifacts/sbom/gateway.spdx.json
	syft scan dir:./web -o spdx-json=artifacts/sbom/web.spdx.json
	@echo "SBOMs written to artifacts/sbom/*.spdx.json"
```

- [ ] **Step 3: Verify the workflow lints**

Run:
```bash
cd /Users/kevinkeller/Desktop/lq-ai
actionlint .github/workflows/release.yml 2>&1 || echo "actionlint not installed; install via 'brew install actionlint' or skip"
```

Expected: no errors. If `actionlint` isn't installed, skip and trust the YAML hand-validation (the syntax above is standard).

- [ ] **Step 4: Confirm Makefile targets render**

Run:
```bash
make -n helm-lint helm-template sbom release-dryrun 2>&1
```

Expected: each prints the command it would run (no execution because `-n` is dry-run). No "No rule to make target" errors.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/release.yml Makefile
git commit -s -m "$(cat <<'EOF'
feat(ci): scaffold release workflow + container build foundation

Adds .github/workflows/release.yml triggered on v*.*.* tag push and
workflow_dispatch (dry-run). Matrix builds api/gateway/web container
images and pushes to ghcr.io/legalquants/lq-ai-* on real tag push;
workflow_dispatch with dry_run=true builds without pushing.

Adds Makefile targets sbom, helm-lint, helm-template, release-dryrun
as local convenience wrappers for Phase E artifacts.

Permissions: contents:read, packages:write, id-token:write,
attestations:write — id-token + attestations are required by SLSA
provenance (T2) and sigstore keyless signing (T3); they are inert
until those tasks land.

Refs Phase E plan T0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

- [ ] **Step 6: Verify commit shape**

Run:
```bash
git log -1 --format=fuller
```

Expected: `Signed-off-by:` line present, `Co-Authored-By:` trailer in body.

---

## Task 1: SBOM generation step (Syft → SPDX JSON)

**Files:**
- Modify: `.github/workflows/release.yml` (append sbom job)

**Background:**
Anchore's `sbom-action` wraps Syft. Generates SPDX JSON 2.3 for each image (covers Python + JS deps + OS layers). The output filename pattern is `{service}.spdx.json` and is uploaded as a workflow artifact. T3 will later sign this artifact with cosign.

- [ ] **Step 1: Append the sbom job to release.yml**

Edit `.github/workflows/release.yml` and add a new `sbom` job after the existing `build-and-push` job (inside the `jobs:` map, at the same indent level as `build-and-push:`):

```yaml
  sbom:
    name: SBOM ${{ matrix.service }}
    needs: build-and-push
    if: ${{ github.event_name == 'push' || !inputs.dry_run }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        service: [api, gateway, web]
    permissions:
      contents: read
      packages: read
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Resolve image tag
        id: tag
        run: |
          if [[ "${GITHUB_REF}" == refs/tags/v* ]]; then
            echo "tag=${GITHUB_REF#refs/tags/}" >> "$GITHUB_OUTPUT"
          else
            echo "tag=dryrun-${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
          fi

      - name: Generate SBOM (SPDX JSON)
        uses: anchore/sbom-action@v0
        with:
          image: ${{ env.REGISTRY }}/${{ env.IMAGE_OWNER }}/lq-ai-${{ matrix.service }}:${{ steps.tag.outputs.tag }}
          format: spdx-json
          output-file: ${{ matrix.service }}.spdx.json
          upload-artifact: true
          upload-artifact-retention: 90

      - name: Verify SBOM is non-empty
        run: |
          test -s ${{ matrix.service }}.spdx.json
          jq -e '.packages | length > 0' ${{ matrix.service }}.spdx.json > /dev/null
```

- [ ] **Step 2: Lint the workflow**

Run:
```bash
actionlint .github/workflows/release.yml 2>&1 || echo "actionlint not installed; relying on hand-validation"
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -s -m "$(cat <<'EOF'
feat(ci): SBOM generation (SPDX JSON) via Syft

Adds sbom matrix job to release.yml that runs after build-and-push.
For each of api/gateway/web, anchore/sbom-action scans the built
image and emits {service}.spdx.json. Uploaded as workflow artifacts
with 90-day retention.

Verification step asserts the JSON is non-empty and has at least one
package entry — catches silent Syft failures that produce empty SBOMs.

Refs Phase E plan T1. Per docs/security/README.md M1 contract.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 2: SLSA build provenance attestation (Level 3)

**Files:**
- Modify: `.github/workflows/release.yml` (append slsa-provenance step inside build-and-push)

**Background:**
`actions/attest-build-provenance` (GitHub-native) generates a SLSA L3 in-toto attestation per image and attaches it to the GitHub OIDC identity of the workflow run. The attestation is uploaded to the GitHub Attestations Store and is verifiable via `gh attestation verify` or `cosign verify-attestation`. SLSA L3 is achievable because the build is hosted on GitHub-managed runners with an isolated execution environment and the attestation is non-falsifiable (signed by Fulcio under workflow OIDC).

The action needs the image digest, which `docker/build-push-action` exposes as `steps.build.outputs.digest`.

- [ ] **Step 1: Append provenance step inside build-and-push job**

Edit `.github/workflows/release.yml` and add this step at the end of the `build-and-push` job's `steps:` list (after the existing "Build and push" step):

```yaml
      - name: Generate SLSA build provenance
        if: ${{ github.event_name == 'push' || !inputs.dry_run }}
        uses: actions/attest-build-provenance@v1
        with:
          subject-name: ${{ env.REGISTRY }}/${{ env.IMAGE_OWNER }}/lq-ai-${{ matrix.service }}
          subject-digest: ${{ steps.build.outputs.digest }}
          push-to-registry: true
```

- [ ] **Step 2: Lint the workflow**

Run:
```bash
actionlint .github/workflows/release.yml 2>&1 || echo "actionlint not installed"
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -s -m "$(cat <<'EOF'
feat(ci): SLSA build provenance (Level 3) via attest-build-provenance

Adds actions/attest-build-provenance step at the end of build-and-push
for each container image. Generates an in-toto attestation signed by
Fulcio under the workflow's OIDC identity and pushes it to the
registry alongside the image (push-to-registry: true).

SLSA Level 3 is reached because:
- Build runs on GitHub-hosted runners (isolated build environment)
- Provenance is non-falsifiable (signed by Fulcio, not by a repo secret)
- Subject digest is captured at the moment of build

Verifiable post-release via:
  gh attestation verify oci://ghcr.io/.../lq-ai-api:vX.Y.Z \\
    --owner legalquants

Skipped when workflow_dispatch fires with dry_run=true (no push, no
provenance).

Refs Phase E plan T2. Per docs/security/README.md M1 contract.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 3: Cosign keyless signing of images + SBOM + provenance

**Files:**
- Modify: `.github/workflows/release.yml` (append sign job)

**Background:**
Sigstore keyless signing: cosign requests a short-lived signing cert from Fulcio, presenting the workflow's OIDC token. The cert is bound to the workflow's identity (`https://github.com/legalquants/lq-ai/.github/workflows/release.yml@refs/tags/vX.Y.Z`). The signature is recorded in the Rekor transparency log. No long-lived private key exists.

We sign three things per service:
1. The container image (cosign sign).
2. The SBOM blob (cosign sign-blob → record attestation).
3. The provenance — already signed by `attest-build-provenance` in T2, no separate step.

- [ ] **Step 1: Append sign job to release.yml**

Edit `.github/workflows/release.yml` and add a new `sign` job (inside `jobs:`, at the same indent level as `build-and-push:`):

```yaml
  sign:
    name: Cosign ${{ matrix.service }}
    needs: [build-and-push, sbom]
    runs-on: ubuntu-latest
    if: ${{ github.event_name == 'push' || !inputs.dry_run }}
    strategy:
      fail-fast: false
      matrix:
        service: [api, gateway, web]
    permissions:
      contents: read
      packages: write
      id-token: write
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Resolve image tag
        id: tag
        run: |
          if [[ "${GITHUB_REF}" == refs/tags/v* ]]; then
            echo "tag=${GITHUB_REF#refs/tags/}" >> "$GITHUB_OUTPUT"
          else
            echo "tag=dryrun-${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
          fi

      - name: Install cosign
        uses: sigstore/cosign-installer@v3
        with:
          cosign-release: v2.4.0

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Download SBOM artifact
        uses: actions/download-artifact@v4
        with:
          name: ${{ matrix.service }}.spdx.json
          path: ./sbom

      - name: Sign container image (keyless)
        run: |
          cosign sign --yes \
            ${{ env.REGISTRY }}/${{ env.IMAGE_OWNER }}/lq-ai-${{ matrix.service }}:${{ steps.tag.outputs.tag }}

      - name: Sign SBOM and attach as attestation
        run: |
          cosign attest --yes \
            --predicate ./sbom/${{ matrix.service }}.spdx.json \
            --type spdxjson \
            ${{ env.REGISTRY }}/${{ env.IMAGE_OWNER }}/lq-ai-${{ matrix.service }}:${{ steps.tag.outputs.tag }}
```

- [ ] **Step 2: Lint the workflow**

Run:
```bash
actionlint .github/workflows/release.yml 2>&1 || echo "actionlint not installed"
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -s -m "$(cat <<'EOF'
feat(ci): cosign keyless signing of images + SBOM attestations

Adds sign job to release.yml that runs after build-and-push + sbom.
For each of api/gateway/web:
- cosign sign signs the container image with a short-lived Fulcio
  cert bound to the workflow's OIDC identity
- cosign attest binds the SBOM as a spdxjson-type attestation to the
  same image digest

No long-lived private key exists. Signatures and attestations are
recorded in the Rekor transparency log and stored in the registry
alongside the image.

Job skipped when workflow_dispatch fires with dry_run=true.

Verify per docs/security/README.md:
  cosign verify --certificate-identity-regexp \\
    "https://github.com/legalquants/lq-ai" \\
    --certificate-oidc-issuer \\
    https://token.actions.githubusercontent.com \\
    ghcr.io/legalquants/lq-ai-api:vX.Y.Z

Refs Phase E plan T3. Per docs/security/README.md M1 contract.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 4: Helm chart at `deploy/helm/lq-ai/`

**Files:**
- Create: `deploy/helm/lq-ai/Chart.yaml`
- Create: `deploy/helm/lq-ai/values.yaml`
- Create: `deploy/helm/lq-ai/values-example.yaml`
- Create: `deploy/helm/lq-ai/NOTES.txt`
- Create: `deploy/helm/lq-ai/.helmignore`
- Create: `deploy/helm/lq-ai/templates/_helpers.tpl`
- Create: `deploy/helm/lq-ai/templates/configmap-gateway.yaml`
- Create: `deploy/helm/lq-ai/templates/secret-refs.yaml`
- Create: `deploy/helm/lq-ai/templates/serviceaccount.yaml`
- Create: `deploy/helm/lq-ai/templates/deployment-api.yaml`
- Create: `deploy/helm/lq-ai/templates/deployment-gateway.yaml`
- Create: `deploy/helm/lq-ai/templates/deployment-web.yaml`
- Create: `deploy/helm/lq-ai/templates/statefulset-postgres.yaml`
- Create: `deploy/helm/lq-ai/templates/statefulset-redis.yaml`
- Create: `deploy/helm/lq-ai/templates/statefulset-minio.yaml`
- Create: `deploy/helm/lq-ai/templates/service-api.yaml`
- Create: `deploy/helm/lq-ai/templates/service-gateway.yaml`
- Create: `deploy/helm/lq-ai/templates/service-web.yaml`
- Create: `deploy/helm/lq-ai/templates/service-postgres.yaml`
- Create: `deploy/helm/lq-ai/templates/service-redis.yaml`
- Create: `deploy/helm/lq-ai/templates/service-minio.yaml`
- Create: `deploy/helm/lq-ai/templates/ingress.yaml`

**Background:**
The chart mirrors `docker-compose.yml` 1-to-1 in service shape: 7 services (postgres, redis, minio, gateway, api, ingest-worker, web). For Phase E we ship api/gateway/web as Deployments; postgres/redis/minio as StatefulSets with PersistentVolumeClaims; ingest-worker as a Deployment (or omit and let operators run a CronJob — verify with implementer; default to Deployment to mirror compose).

The `gateway.yaml` config goes into a ConfigMap (operators edit values.yaml `gateway.config` or supply their own file). Provider API keys come from Kubernetes Secrets — `secretRefs.providerKeys` in values.yaml names them; the deployment env mounts them. No keys baked into the chart.

Operator-key swap-in for cosign is documented in NOTES.txt as a values knob (e.g., `release.signing.mode: keyless | operator-key`) but not implemented as a chart-time behavior — it's a release-pipeline concern, not a deployment-time concern. Just a doc note.

This task is the heaviest in Phase E. Suggested decomposition: commit Chart.yaml + values.yaml + helpers + NOTES.txt + .helmignore as one foundational commit; then commit each service group (storage / app / web) as separate commits; then the ingress + verification commit at the end. ~4 commits for T4 alone.

- [ ] **Step 1: Create chart foundation**

Create `deploy/helm/lq-ai/Chart.yaml`:

```yaml
apiVersion: v2
name: lq-ai
description: LQ.AI — open-source AI platform for in-house legal teams.
type: application
version: 0.1.0
appVersion: "0.1.0"
keywords:
  - legal
  - ai
  - llm
  - rag
home: https://github.com/legalquants/lq-ai
sources:
  - https://github.com/legalquants/lq-ai
maintainers:
  - name: LegalQuants
    url: https://github.com/legalquants
icon: https://raw.githubusercontent.com/legalquants/lq-ai/main/docs/assets/logo.png
```

Create `deploy/helm/lq-ai/.helmignore`:

```
.DS_Store
.git/
.gitignore
*.tgz
.vscode/
.idea/
*.swp
*.bak
*.tmp
*~
```

Create `deploy/helm/lq-ai/NOTES.txt`:

```
Thanks for installing LQ.AI {{ .Chart.AppVersion }}.

Verification of release artifacts (per docs/security/README.md):

  cosign verify \
    --certificate-identity-regexp "https://github.com/legalquants/lq-ai" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    ghcr.io/legalquants/lq-ai-api:{{ .Values.image.tag | default .Chart.AppVersion }}

Components installed:
- Postgres (pgvector/pgvector:pg16) — primary store
- Redis (redis:7-alpine)             — cache + queue
- MinIO (minio/minio:latest)         — object storage
- Gateway                            — Inference Gateway (security boundary)
- API                                — FastAPI backend
- Web                                — OpenWebUI fork

First-run admin password is printed by the api Pod at first boot. Retrieve with:
  kubectl logs -n {{ .Release.Namespace }} \
    -l app.kubernetes.io/component=api \
    --tail=200 | grep "First-run admin password"

Default web URL (port-forward):
  kubectl port-forward -n {{ .Release.Namespace }} svc/{{ include "lq-ai.fullname" . }}-web 8080:80
  open http://localhost:8080

If you forked LQ.AI and want to use operator-controlled cosign signing
(instead of keyless OIDC), see docs/security/releases/README.md §"Operator-key signing".

Configure your providers:
  helm get values {{ .Release.Name }} -n {{ .Release.Namespace }}
Edit gateway.config in values.yaml and helm upgrade.
```

Create `deploy/helm/lq-ai/templates/_helpers.tpl`:

```yaml
{{/*
Common name helpers — mirrors the standard Helm chart pattern.
*/}}
{{- define "lq-ai.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "lq-ai.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "lq-ai.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "lq-ai.labels" -}}
helm.sh/chart: {{ include "lq-ai.chart" . }}
{{ include "lq-ai.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "lq-ai.selectorLabels" -}}
app.kubernetes.io/name: {{ include "lq-ai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
```

Create `deploy/helm/lq-ai/values.yaml`:

```yaml
# LQ.AI Helm chart — defaults
# Operators copy values-example.yaml to a local file, edit, and pass via
# helm install lq-ai ./deploy/helm/lq-ai -f my-values.yaml.

nameOverride: ""
fullnameOverride: ""

image:
  registry: ghcr.io
  owner: legalquants
  tag: ""              # defaults to .Chart.AppVersion
  pullPolicy: IfNotPresent

# Postgres
postgres:
  enabled: true
  image: pgvector/pgvector:pg16
  storage: 20Gi
  storageClass: ""     # use cluster default if empty
  database: lq_ai
  user: lq_ai
  # Reference an existing Secret with key POSTGRES_PASSWORD; do NOT inline.
  passwordSecretRef:
    name: lq-ai-postgres
    key: password

# Redis
redis:
  enabled: true
  image: redis:7-alpine
  storage: 5Gi
  storageClass: ""

# MinIO
minio:
  enabled: true
  image: minio/minio:latest
  storage: 50Gi
  storageClass: ""
  rootUser: lq_ai
  rootPasswordSecretRef:
    name: lq-ai-minio
    key: password

# Gateway
gateway:
  replicaCount: 1
  resources:
    requests: { cpu: 200m, memory: 256Mi }
    limits:   { cpu: 1000m, memory: 1Gi }
  # Inline gateway.yaml. Operators normally override via values-example.yaml.
  config: |
    providers: []
  # Provider API keys are mounted as env-vars from a Secret the operator creates.
  # Map env-var name -> secretRef.
  providerKeys: {}
    # Example:
    # ANTHROPIC_API_KEY:
    #   secretName: lq-ai-provider-keys
    #   key: anthropic
  # JWT signing secret + gateway shared secret
  authSecretRef:
    name: lq-ai-auth
    jwtKey: jwt-secret
    gatewayKey: gateway-key

# API
api:
  replicaCount: 1
  resources:
    requests: { cpu: 200m, memory: 256Mi }
    limits:   { cpu: 1000m, memory: 2Gi }

# Web
web:
  replicaCount: 1
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits:   { cpu: 500m, memory: 1Gi }

# Ingress
ingress:
  enabled: false
  className: ""
  annotations: {}
  hosts:
    - host: lq-ai.local
      paths:
        - path: /
          pathType: Prefix
  tls: []

serviceAccount:
  create: true
  annotations: {}
  name: ""
```

Create `deploy/helm/lq-ai/values-example.yaml`:

```yaml
# Example values for a small self-hosted deployment.
# Operators MUST create the referenced secrets before installing:
#
#   kubectl create secret generic lq-ai-postgres \
#     --from-literal=password="$(openssl rand -hex 32)"
#   kubectl create secret generic lq-ai-minio \
#     --from-literal=password="$(openssl rand -hex 32)"
#   kubectl create secret generic lq-ai-auth \
#     --from-literal=jwt-secret="$(openssl rand -hex 32)" \
#     --from-literal=gateway-key="$(openssl rand -hex 32)"
#   kubectl create secret generic lq-ai-provider-keys \
#     --from-literal=anthropic="sk-ant-..." \
#     --from-literal=openai="sk-..."

image:
  tag: "v0.1.0"

gateway:
  config: |
    providers:
      - name: anthropic-prod
        adapter: anthropic
        api_key_env: ANTHROPIC_API_KEY
        models:
          - claude-opus-4-7
          - claude-sonnet-4-6
          - claude-haiku-4-5
  providerKeys:
    ANTHROPIC_API_KEY:
      secretName: lq-ai-provider-keys
      key: anthropic

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: lq-ai.example.com
      paths:
        - path: /
          pathType: Prefix
```

- [ ] **Step 2: Lint and template (foundation)**

Run:
```bash
cd /Users/kevinkeller/Desktop/lq-ai
helm lint deploy/helm/lq-ai 2>&1 | tail -10
```

Expected: `0 chart(s) failed`. Template warnings about missing templates are OK at this checkpoint — service templates land in subsequent steps.

- [ ] **Step 3: Commit foundation**

```bash
git add deploy/helm/lq-ai/Chart.yaml \
        deploy/helm/lq-ai/values.yaml \
        deploy/helm/lq-ai/values-example.yaml \
        deploy/helm/lq-ai/NOTES.txt \
        deploy/helm/lq-ai/.helmignore \
        deploy/helm/lq-ai/templates/_helpers.tpl
git commit -s -m "$(cat <<'EOF'
feat(deploy): Helm chart foundation for lq-ai

Adds deploy/helm/lq-ai/ scaffold: Chart.yaml (apiVersion v2, type
application), values.yaml (defaults for all 7 services), values-
example.yaml (small self-hosted deployment recipe), NOTES.txt (post-
install instructions including cosign verify and admin-password
retrieval), .helmignore, _helpers.tpl (name + label helpers).

Provider API keys come from operator-managed Kubernetes Secrets
referenced by name + key. No keys baked into the chart. The chart
mirrors docker-compose.yml service-shape 1-to-1.

Distribution model: in-repo only (operators clone the repo and
helm install ./deploy/helm/lq-ai). No chart registry or Helm repo
this cycle.

Refs Phase E plan T4 step 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

- [ ] **Step 4: Create storage StatefulSets + services**

Create `deploy/helm/lq-ai/templates/statefulset-postgres.yaml`:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {{ include "lq-ai.fullname" . }}-postgres
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: postgres
spec:
  serviceName: {{ include "lq-ai.fullname" . }}-postgres
  replicas: 1
  selector:
    matchLabels:
      {{- include "lq-ai.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: postgres
  template:
    metadata:
      labels:
        {{- include "lq-ai.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: postgres
    spec:
      containers:
        - name: postgres
          image: {{ .Values.postgres.image }}
          ports:
            - name: postgres
              containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: {{ .Values.postgres.database }}
            - name: POSTGRES_USER
              value: {{ .Values.postgres.user }}
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.postgres.passwordSecretRef.name }}
                  key: {{ .Values.postgres.passwordSecretRef.key }}
          volumeMounts:
            - name: pgdata
              mountPath: /var/lib/postgresql/data
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "{{ .Values.postgres.user }}", "-d", "{{ .Values.postgres.database }}"]
            initialDelaySeconds: 5
            periodSeconds: 5
  volumeClaimTemplates:
    - metadata:
        name: pgdata
      spec:
        accessModes: ["ReadWriteOnce"]
        {{- if .Values.postgres.storageClass }}
        storageClassName: {{ .Values.postgres.storageClass | quote }}
        {{- end }}
        resources:
          requests:
            storage: {{ .Values.postgres.storage }}
```

Create `deploy/helm/lq-ai/templates/statefulset-redis.yaml`:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {{ include "lq-ai.fullname" . }}-redis
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: redis
spec:
  serviceName: {{ include "lq-ai.fullname" . }}-redis
  replicas: 1
  selector:
    matchLabels:
      {{- include "lq-ai.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: redis
  template:
    metadata:
      labels:
        {{- include "lq-ai.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: redis
    spec:
      containers:
        - name: redis
          image: {{ .Values.redis.image }}
          args: ["redis-server", "--appendonly", "yes"]
          ports:
            - name: redis
              containerPort: 6379
          volumeMounts:
            - name: redisdata
              mountPath: /data
          readinessProbe:
            exec:
              command: ["redis-cli", "ping"]
            initialDelaySeconds: 5
            periodSeconds: 5
  volumeClaimTemplates:
    - metadata:
        name: redisdata
      spec:
        accessModes: ["ReadWriteOnce"]
        {{- if .Values.redis.storageClass }}
        storageClassName: {{ .Values.redis.storageClass | quote }}
        {{- end }}
        resources:
          requests:
            storage: {{ .Values.redis.storage }}
```

Create `deploy/helm/lq-ai/templates/statefulset-minio.yaml`:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {{ include "lq-ai.fullname" . }}-minio
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: minio
spec:
  serviceName: {{ include "lq-ai.fullname" . }}-minio
  replicas: 1
  selector:
    matchLabels:
      {{- include "lq-ai.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: minio
  template:
    metadata:
      labels:
        {{- include "lq-ai.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: minio
    spec:
      containers:
        - name: minio
          image: {{ .Values.minio.image }}
          args: ["server", "/data", "--console-address", ":9001"]
          ports:
            - { name: api, containerPort: 9000 }
            - { name: console, containerPort: 9001 }
          env:
            - name: MINIO_ROOT_USER
              value: {{ .Values.minio.rootUser }}
            - name: MINIO_ROOT_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.minio.rootPasswordSecretRef.name }}
                  key: {{ .Values.minio.rootPasswordSecretRef.key }}
          volumeMounts:
            - name: miniodata
              mountPath: /data
          readinessProbe:
            httpGet:
              path: /minio/health/live
              port: api
            initialDelaySeconds: 10
            periodSeconds: 10
  volumeClaimTemplates:
    - metadata:
        name: miniodata
      spec:
        accessModes: ["ReadWriteOnce"]
        {{- if .Values.minio.storageClass }}
        storageClassName: {{ .Values.minio.storageClass | quote }}
        {{- end }}
        resources:
          requests:
            storage: {{ .Values.minio.storage }}
```

Create `deploy/helm/lq-ai/templates/service-postgres.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "lq-ai.fullname" . }}-postgres
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: postgres
spec:
  type: ClusterIP
  ports:
    - port: 5432
      targetPort: postgres
      name: postgres
  selector:
    {{- include "lq-ai.selectorLabels" . | nindent 4 }}
    app.kubernetes.io/component: postgres
```

Create `deploy/helm/lq-ai/templates/service-redis.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "lq-ai.fullname" . }}-redis
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: redis
spec:
  type: ClusterIP
  ports:
    - port: 6379
      targetPort: redis
      name: redis
  selector:
    {{- include "lq-ai.selectorLabels" . | nindent 4 }}
    app.kubernetes.io/component: redis
```

Create `deploy/helm/lq-ai/templates/service-minio.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "lq-ai.fullname" . }}-minio
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: minio
spec:
  type: ClusterIP
  ports:
    - { port: 9000, targetPort: api,     name: api }
    - { port: 9001, targetPort: console, name: console }
  selector:
    {{- include "lq-ai.selectorLabels" . | nindent 4 }}
    app.kubernetes.io/component: minio
```

Run:
```bash
make helm-lint && make helm-template > /tmp/lq-ai-template.yaml 2>&1
echo "exit=$?"
grep -c "^kind:" /tmp/lq-ai-template.yaml
```

Expected: lint passes, template renders, at least 6 Kubernetes resources (3 StatefulSets + 3 Services) so `grep -c` ≥ 6.

Commit:
```bash
git add deploy/helm/lq-ai/templates/statefulset-*.yaml \
        deploy/helm/lq-ai/templates/service-postgres.yaml \
        deploy/helm/lq-ai/templates/service-redis.yaml \
        deploy/helm/lq-ai/templates/service-minio.yaml
git commit -s -m "$(cat <<'EOF'
feat(deploy): Helm storage layer — postgres / redis / minio

Adds StatefulSets for postgres (pgvector/pgvector:pg16), redis
(redis:7-alpine), and minio (minio/minio:latest) — each with a
PersistentVolumeClaim template, readiness probe, and a ClusterIP
Service.

Passwords and root credentials are sourced from operator-created
Kubernetes Secrets via secretRef name+key — none inline in values.

Refs Phase E plan T4 step 4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

- [ ] **Step 5: Create application Deployments + services (api / gateway / web)**

Create `deploy/helm/lq-ai/templates/configmap-gateway.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "lq-ai.fullname" . }}-gateway
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: gateway
data:
  gateway.yaml: |-
{{ .Values.gateway.config | indent 4 }}
```

Create `deploy/helm/lq-ai/templates/serviceaccount.yaml`:

```yaml
{{- if .Values.serviceAccount.create -}}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ default (include "lq-ai.fullname" .) .Values.serviceAccount.name }}
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
  {{- with .Values.serviceAccount.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end }}
```

Create `deploy/helm/lq-ai/templates/deployment-gateway.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "lq-ai.fullname" . }}-gateway
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: gateway
spec:
  replicas: {{ .Values.gateway.replicaCount }}
  selector:
    matchLabels:
      {{- include "lq-ai.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: gateway
  template:
    metadata:
      labels:
        {{- include "lq-ai.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: gateway
    spec:
      serviceAccountName: {{ default (include "lq-ai.fullname" .) .Values.serviceAccount.name }}
      containers:
        - name: gateway
          image: "{{ .Values.image.registry }}/{{ .Values.image.owner }}/lq-ai-gateway:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 8001
          env:
            - name: LQ_AI_GATEWAY_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.gateway.authSecretRef.name }}
                  key: {{ .Values.gateway.authSecretRef.gatewayKey }}
            {{- range $envName, $ref := .Values.gateway.providerKeys }}
            - name: {{ $envName }}
              valueFrom:
                secretKeyRef:
                  name: {{ $ref.secretName }}
                  key: {{ $ref.key }}
            {{- end }}
          volumeMounts:
            - name: config
              mountPath: /etc/lq-ai/gateway.yaml
              subPath: gateway.yaml
              readOnly: true
          resources:
            {{- toYaml .Values.gateway.resources | nindent 12 }}
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
      volumes:
        - name: config
          configMap:
            name: {{ include "lq-ai.fullname" . }}-gateway
```

Create `deploy/helm/lq-ai/templates/deployment-api.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "lq-ai.fullname" . }}-api
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: api
spec:
  replicas: {{ .Values.api.replicaCount }}
  selector:
    matchLabels:
      {{- include "lq-ai.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: api
  template:
    metadata:
      labels:
        {{- include "lq-ai.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: api
    spec:
      serviceAccountName: {{ default (include "lq-ai.fullname" .) .Values.serviceAccount.name }}
      containers:
        - name: api
          image: "{{ .Values.image.registry }}/{{ .Values.image.owner }}/lq-ai-api:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 8000
          env:
            - name: DATABASE_URL
              value: "postgresql+asyncpg://{{ .Values.postgres.user }}:$(POSTGRES_PASSWORD)@{{ include "lq-ai.fullname" . }}-postgres:5432/{{ .Values.postgres.database }}"
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.postgres.passwordSecretRef.name }}
                  key: {{ .Values.postgres.passwordSecretRef.key }}
            - name: REDIS_URL
              value: "redis://{{ include "lq-ai.fullname" . }}-redis:6379/0"
            - name: MINIO_ENDPOINT
              value: "{{ include "lq-ai.fullname" . }}-minio:9000"
            - name: MINIO_ROOT_USER
              value: {{ .Values.minio.rootUser }}
            - name: MINIO_ROOT_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.minio.rootPasswordSecretRef.name }}
                  key: {{ .Values.minio.rootPasswordSecretRef.key }}
            - name: GATEWAY_URL
              value: "http://{{ include "lq-ai.fullname" . }}-gateway:8001"
            - name: LQ_AI_GATEWAY_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.gateway.authSecretRef.name }}
                  key: {{ .Values.gateway.authSecretRef.gatewayKey }}
            - name: JWT_SECRET
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.gateway.authSecretRef.name }}
                  key: {{ .Values.gateway.authSecretRef.jwtKey }}
          resources:
            {{- toYaml .Values.api.resources | nindent 12 }}
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
```

Create `deploy/helm/lq-ai/templates/deployment-web.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "lq-ai.fullname" . }}-web
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: web
spec:
  replicas: {{ .Values.web.replicaCount }}
  selector:
    matchLabels:
      {{- include "lq-ai.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: web
  template:
    metadata:
      labels:
        {{- include "lq-ai.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: web
    spec:
      serviceAccountName: {{ default (include "lq-ai.fullname" .) .Values.serviceAccount.name }}
      containers:
        - name: web
          image: "{{ .Values.image.registry }}/{{ .Values.image.owner }}/lq-ai-web:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: API_BASE_URL
              value: "http://{{ include "lq-ai.fullname" . }}-api:8000"
          resources:
            {{- toYaml .Values.web.resources | nindent 12 }}
          readinessProbe:
            httpGet:
              path: /
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
```

Create `deploy/helm/lq-ai/templates/service-gateway.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "lq-ai.fullname" . }}-gateway
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: gateway
spec:
  type: ClusterIP
  ports:
    - port: 8001
      targetPort: http
      name: http
  selector:
    {{- include "lq-ai.selectorLabels" . | nindent 4 }}
    app.kubernetes.io/component: gateway
```

Create `deploy/helm/lq-ai/templates/service-api.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "lq-ai.fullname" . }}-api
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: api
spec:
  type: ClusterIP
  ports:
    - port: 8000
      targetPort: http
      name: http
  selector:
    {{- include "lq-ai.selectorLabels" . | nindent 4 }}
    app.kubernetes.io/component: api
```

Create `deploy/helm/lq-ai/templates/service-web.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "lq-ai.fullname" . }}-web
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: web
spec:
  type: ClusterIP
  ports:
    - port: 80
      targetPort: http
      name: http
  selector:
    {{- include "lq-ai.selectorLabels" . | nindent 4 }}
    app.kubernetes.io/component: web
```

Run:
```bash
make helm-lint && make helm-template > /tmp/lq-ai-template.yaml 2>&1
echo "exit=$?"
grep -c "^kind:" /tmp/lq-ai-template.yaml
```

Expected: lint passes, template renders, ≥13 resources (3 StatefulSets + 6 Services + 3 Deployments + 1 ConfigMap = 13; + optional ServiceAccount = 14).

Commit:
```bash
git add deploy/helm/lq-ai/templates/configmap-gateway.yaml \
        deploy/helm/lq-ai/templates/serviceaccount.yaml \
        deploy/helm/lq-ai/templates/deployment-*.yaml \
        deploy/helm/lq-ai/templates/service-gateway.yaml \
        deploy/helm/lq-ai/templates/service-api.yaml \
        deploy/helm/lq-ai/templates/service-web.yaml
git commit -s -m "$(cat <<'EOF'
feat(deploy): Helm application layer — gateway / api / web

Adds Deployments + ClusterIP Services for gateway, api, and web,
plus a ConfigMap that materializes gateway.yaml from
.Values.gateway.config and a ServiceAccount (optional, on by default).

Service wiring mirrors docker-compose:
- gateway 8001 (LQ_AI_GATEWAY_KEY + provider keys from secrets)
- api 8000 (DATABASE_URL composed from postgres svc + secret)
- web 8080 -> svc port 80

Provider API keys flow via .Values.gateway.providerKeys map -> env
vars sourced from operator-created Secrets. No keys inline.

Refs Phase E plan T4 step 5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

- [ ] **Step 6: Create ingress + final lint**

Create `deploy/helm/lq-ai/templates/ingress.yaml`:

```yaml
{{- if .Values.ingress.enabled -}}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "lq-ai.fullname" . }}-web
  labels:
    {{- include "lq-ai.labels" . | nindent 4 }}
    app.kubernetes.io/component: web
  {{- with .Values.ingress.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  {{- if .Values.ingress.className }}
  ingressClassName: {{ .Values.ingress.className }}
  {{- end }}
  {{- if .Values.ingress.tls }}
  tls:
    {{- toYaml .Values.ingress.tls | nindent 4 }}
  {{- end }}
  rules:
    {{- range .Values.ingress.hosts }}
    - host: {{ .host | quote }}
      http:
        paths:
          {{- range .paths }}
          - path: {{ .path }}
            pathType: {{ .pathType }}
            backend:
              service:
                name: {{ include "lq-ai.fullname" $ }}-web
                port:
                  number: 80
          {{- end }}
    {{- end }}
{{- end }}
```

Run the full verification:
```bash
cd /Users/kevinkeller/Desktop/lq-ai
helm lint deploy/helm/lq-ai 2>&1
helm template lq-ai deploy/helm/lq-ai -f deploy/helm/lq-ai/values-example.yaml > /tmp/render.yaml
grep -c "^kind:" /tmp/render.yaml
# Optional: dry-run install (requires a k8s context; skip if none)
# kubectl --dry-run=client apply -f /tmp/render.yaml
```

Expected: lint passes with 0 chart failures, render produces ≥14 resources (foundation + storage + app + 1 Ingress).

Commit:
```bash
git add deploy/helm/lq-ai/templates/ingress.yaml
git commit -s -m "$(cat <<'EOF'
feat(deploy): Helm ingress template (off by default)

Adds optional Ingress template gated on .Values.ingress.enabled.
Routes the configured host(s) to the lq-ai-web Service on port 80.
Supports custom ingressClassName, TLS, and annotations.

Default: ingress disabled. Operators flip enabled: true and supply
the host (and TLS secret if termating TLS at the ingress).

Refs Phase E plan T4 step 6.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 5: `docs/security/threat-model.md` (STRIDE-by-component)

**Files:**
- Create: `docs/security/threat-model.md`

**Background:**
One table, five rows (api / gateway / web / postgres / minio), STRIDE columns: Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege. Each cell names the threat in 1 sentence and the mitigation in 1 sentence, with a cross-reference to PRD §5, ADR 0009, or ADR 0011 where the design intent is documented. Aim for ~1-2 pages total. The implementer should read PRD §5 (Security & Compliance) and ADR 0009 (web-lq-ai shell coexistence) before writing.

- [ ] **Step 1: Read prerequisite docs**

Run:
```bash
cd /Users/kevinkeller/Desktop/lq-ai
grep -n "^##" docs/PRD.md | grep -i "security\|compliance\|threat\|§5"
wc -l docs/adr/0009-web-lq-ai-shell-coexistence.md docs/adr/0011-transparency-first-model-selection.md
```

Expected: PRD §5 section header located. ADRs have content (non-zero line counts).

- [ ] **Step 2: Author the threat model**

Create `docs/security/threat-model.md` with this structure (implementer fills the cells from PRD §5 + the docker-compose service shape):

```markdown
# Threat Model

> **Depth:** Summary-level. STRIDE-by-component for the 5 production services. Named threats + named mitigations with cross-references. Detailed design intent lives in PRD §5 and the ADR series.

## Trust boundaries

LQ.AI runs as 7 services on a single operator-controlled deployment (Docker Compose for dev; Helm/Kubernetes for production per `deploy/helm/lq-ai/`). The Inference Gateway is the only component holding plaintext provider API keys per PRD §4; this defines the primary trust boundary. Everything internal to the operator's deployment is one trust zone; the LLM providers (Anthropic, OpenAI, etc.) are another; the operator's IdP (if integrated) is a third.

```
┌────────────────────────────────────────────────────────────┐
│ Operator deployment                                        │
│  ┌──────┐   ┌─────────┐   ┌──────────┐   ┌────────────┐   │
│  │ web  │──>│   api   │──>│ gateway  │──>│ providers  │   │
│  └──────┘   └────┬────┘   └────┬─────┘   └────────────┘   │
│                  ▼             ▼                          │
│              ┌────────┐    ┌─────────┐                    │
│              │postgres│    │  minio  │                    │
│              └────────┘    └─────────┘                    │
│              ┌────────┐                                   │
│              │ redis  │                                   │
│              └────────┘                                   │
└────────────────────────────────────────────────────────────┘
```

## STRIDE-by-component

| Component | Spoofing | Tampering | Repudiation | Info Disclosure | DoS | Elevation of Privilege |
|---|---|---|---|---|---|---|
| **api** | [fill: e.g., forged JWT → JWT_SECRET rotation per ADR 0002] | [fill: API request body tampering → server-side validation; OpenAPI schema enforcement] | [fill: who deleted a matter → audit_log per docs/db-schema.md §audit_log] | [fill: stolen access token → short-lived JWT + must_change_password gate] | [fill: unauthenticated request flood → rate limit; auth required on all routes] | [fill: tenant boundary crossing → all queries scoped by user_id; RBAC role enum] |
| **gateway** | [fill: forged inference request → LQ_AI_GATEWAY_KEY shared secret in env] | [fill: prompt injection → Anonymization Layer + Tier Derivation per PRD §4] | [fill: which model handled a request → inference_routing_log audit trail] | [fill: provider key exfil → ADR 0011 encrypted-at-rest path; plaintext only in process memory] | [fill: token-cost amplification → per-user/per-tier quotas at gateway] | [fill: tier escalation → tier_floor enforced server-side; operator can't bypass via UI] |
| **web** | [fill: session theft → SameSite=Strict cookies; CSRF token on state-changing routes] | [fill: XSS via skill content → DOMPurify on Markdown; CSP header] | n/a (web does not author audit events) | [fill: localStorage leak of skill data → sanitize what's stored; no provider keys ever in localStorage] | [fill: client-side render bomb → message-length caps from api] | n/a (browser sandbox bounds elevation) |
| **postgres** | n/a (cluster-internal) | [fill: row tampering by a co-located service → least-privilege role per service] | n/a (Postgres logs are operator-managed) | [fill: pgvector embedding leak revealing doc content → row-level scoping by user_id] | [fill: connection exhaustion → connection pool ceiling] | [fill: superuser escalation → operator deploys with non-superuser app role] |
| **minio** | n/a (cluster-internal) | [fill: object tampering → versioned buckets per ADR 0005] | [fill: who uploaded what → audit_log row per upload] | [fill: cross-tenant object access → object keys scoped by `<user_id>/<project_id>/...`] | [fill: storage exhaustion → operator-set quota per bucket] | [fill: MinIO admin escalation → root credentials only in operator-managed Secret] |

## Out-of-scope threats

- **Compromise of the operator's host / OS / supervisor.** LQ.AI assumes the operator's deployment substrate is trusted. Container escape, OS-level compromise, and physical access are operator responsibilities.
- **Compromise of an LLM provider.** Gateway minimizes blast radius (Anonymization, Tier Derivation, per-provider isolation), but a compromised provider that already received unredacted content is outside our trust envelope.
- **Compromise of operator-controlled secrets.** If JWT_SECRET or gateway-key leaks, an attacker can forge tokens. Operators rotate per their own runbooks; the gateway-config-hot-reload path (ADR 0010) supports rotation without restart.

## Cross-references

- [PRD §5 Security & Compliance](../PRD.md#5-security--compliance) — design intent.
- [ADR 0002 Backend-owned auth](../adr/0002-backend-owned-auth.md) — JWT scheme + session model.
- [ADR 0005 File storage soft-delete + key scheme](../adr/0005-file-storage-soft-delete-and-key-scheme.md) — object key tenancy.
- [ADR 0009 Web + LQ.AI shell coexistence](../adr/0009-web-lq-ai-shell-coexistence.md) — frontend trust boundary.
- [ADR 0010 Gateway config hot-reload](../adr/0010-gateway-config-hot-reload.md) — secret rotation.
- [ADR 0011 Transparency-first model selection](../adr/0011-transparency-first-model-selection.md) — encrypted-at-rest provider keys.
- [Vulnerability disclosure policy](../../SECURITY.md) — coordinated disclosure process.

## Update cadence

This threat model is refreshed each minor release when a new component lands or a trust boundary moves. The current version covers M1 (api, gateway, web, postgres, redis, minio). Future cycles add the Word add-in (M3) and the Compliance Alignment Pack mappings.
```

NOTE for implementer: each cell starting with `[fill: ...]` is a concrete prompt — go read the named code/doc, distill the actual threat and mitigation into 1 sentence each, replace the bracket with the result. Do not leave any `[fill: ...]` markers in the committed file.

- [ ] **Step 3: Verify no fill-markers remain**

Run:
```bash
cd /Users/kevinkeller/Desktop/lq-ai
grep -c "\[fill:" docs/security/threat-model.md
```

Expected: `0`.

- [ ] **Step 4: Commit**

```bash
git add docs/security/threat-model.md
git commit -s -m "$(cat <<'EOF'
docs(security): STRIDE-by-component threat model

Adds docs/security/threat-model.md per PRD §7.5 + the M1 contract
in docs/security/README.md. STRIDE table covers api/gateway/web/
postgres/minio with named threats + mitigations; cross-references
PRD §5 and the ADR series for design intent.

Out-of-scope threats (host compromise, provider compromise, leaked
operator secrets) are documented explicitly so the trust envelope
is unambiguous.

Refs Phase E plan T5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 6: `docs/security/cryptography.md`

**Files:**
- Create: `docs/security/cryptography.md`

**Background:**
Documents primitives used, key lifecycle, and known limitations. Anchors:
- **JWT** for session auth — algorithm, signing secret lifecycle, claim shape. See `api/app/auth/` (verify path with implementer).
- **Fernet** for at-rest provider-key encryption — see `docs/security/encrypted-keys.md` and `gateway/app/secrets.py`.
- **TLS** for in-transit between services — operator-deployed (chart + ingress); not the application's responsibility but documented.
- **bcrypt or argon2** for user-password storage — verify against actual implementation.
- **Random tokens** for must-change-password gate + first-run admin password — verify generator (Python `secrets` module typically).

- [ ] **Step 1: Survey the primitives in code**

Run:
```bash
cd /Users/kevinkeller/Desktop/lq-ai
grep -rn "jwt\.encode\|jwt\.decode\|HS256\|RS256" api/app/ 2>&1 | head -10
grep -rn "bcrypt\|argon2\|pbkdf2" api/app/ 2>&1 | head -10
grep -rn "secrets\.token_\|os\.urandom" api/app/ 2>&1 | head -10
grep -rn "Fernet" gateway/app/ 2>&1 | head -10
```

Expected: real hits for each. Note the file + line numbers for the doc cross-references.

- [ ] **Step 2: Author the doc**

Create `docs/security/cryptography.md`:

```markdown
# Cryptography

> **Scope:** Cryptographic primitives used by LQ.AI, key lifecycle, and known limitations. Intended for operators evaluating the system for procurement, and for security reviewers tracing a specific control.

## Primitives in use

| Purpose | Algorithm | Library | Reference |
|---|---|---|---|
| Session tokens | JWT HS256 | PyJWT | [api/app/auth/...] (link to actual file) |
| User passwords (at rest) | [bcrypt or argon2 — fill in] | [library — fill in] | [api/app/auth/...] |
| Provider API keys (at rest) | Fernet (AES-128-CBC + HMAC-SHA256, RFC-compliant) | `cryptography` | [docs/security/encrypted-keys.md](encrypted-keys.md), [ADR 0011 §Encrypted-at-rest provider keys](../adr/0011-transparency-first-model-selection.md#encrypted-at-rest-provider-keys), `gateway/app/secrets.py` |
| Random tokens (admin password, must-change gate) | CSPRNG | Python `secrets` | [api/app/cli.py] (link) |
| In-transit between services | TLS 1.2+ | (operator-deployed via ingress) | [Helm chart Ingress](../../deploy/helm/lq-ai/templates/ingress.yaml) |

## Key lifecycle

### Session signing secret (JWT_SECRET)

- **Generation:** operator-supplied at deployment time. Recommended: `openssl rand -hex 32` (256 bits).
- **Storage:** Kubernetes Secret `lq-ai-auth` key `jwt-secret`; Docker compose `.env` `JWT_SECRET`.
- **Rotation:** restart api with a new JWT_SECRET. Existing sessions invalidate; users re-authenticate. No graceful overlap window in M1.
- **Disclosure impact:** an attacker with JWT_SECRET forges any user's session. Treat as a "rotate immediately + log out all users" event.

### Master key for Fernet-wrapped provider keys

- **Generation:** operator-controlled. See [encrypted-keys.md §Bootstrap](encrypted-keys.md).
- **Storage:** operator's secrets vault. Gateway reads the plaintext master key from an env var at process start; never on disk.
- **Rotation:** see [encrypted-keys.md §Rotation](encrypted-keys.md) — re-encrypt every provider key under the new master before restarting.
- **Disclosure impact:** an attacker with the master key can decrypt every `api_key_encrypted` in `gateway.yaml`. Treat as a "rotate master + re-encrypt all provider keys" event.

### Gateway shared secret (LQ_AI_GATEWAY_KEY)

- **Generation:** operator-supplied at deployment time. Recommended: `openssl rand -hex 32`.
- **Storage:** Kubernetes Secret `lq-ai-auth` key `gateway-key`; Docker compose `.env` `LQ_AI_GATEWAY_KEY`.
- **Rotation:** see [ADR 0010 Gateway config hot-reload](../adr/0010-gateway-config-hot-reload.md) — gateway picks up the new key without restart; api must be restarted with the new value.
- **Disclosure impact:** an attacker with this key can call the gateway directly, bypassing api-level audit logging. Rotate immediately on suspected disclosure.

### Provider API keys

Two paths, per [ADR 0011](../adr/0011-transparency-first-model-selection.md):

- `api_key_env` — operator passes the plaintext key as an env var. Plaintext exists in env at gateway boot.
- `api_key_encrypted` — operator runs `python -m app.cli encrypt-key` to produce a Fernet ciphertext; gateway decrypts in memory at adapter-build time. Plaintext never on disk after the encryption helper exits.

## Known limitations

- **HS256 vs RS256.** M1 uses HS256 (symmetric). Operators with elaborate multi-service signing schemes may prefer RS256; we'll consider it for M2 if there is operator demand.
- **No session-overlap during JWT_SECRET rotation.** Rotation logs everyone out. Acceptable for M1's deployment scale; we may add a graceful overlap window if operator deployments grow.
- **Fernet uses AES-CBC, not AEAD-GCM.** Fernet is a documented profile (cryptography.io's Fernet construction) that does provide authenticated encryption via HMAC-SHA256. Operators preferring NIST-standardized AEAD-GCM can swap in libsodium-based encryption by replacing `gateway/app/secrets.py`'s implementation; the chart and CLI continue to work as long as the wire format is documented.
- **TLS termination is operator-managed.** LQ.AI does not terminate TLS in any container; ingress or operator-supplied reverse proxy handles certs. This is by design (cert management is operator policy, not application policy) but means the application has no telemetry on TLS-handshake-level threats.
- **No HSM / KMS integration in M1.** The master key for Fernet is a env-var-held secret. Operators with HSM/KMS requirements can fork `gateway/app/secrets.py` to source the master key from cloud KMS; we may ship a built-in adapter in a future milestone.
```

NOTE for implementer: replace `[bcrypt or argon2 — fill in]` and the `[api/app/...]` link placeholders with what the survey in Step 1 found. Do not commit with placeholders.

- [ ] **Step 3: Verify no placeholders remain**

Run:
```bash
grep -E "\[bcrypt or argon2 — fill in\]|\[api/app/\.\.\.\]|\[library — fill in\]" docs/security/cryptography.md
```

Expected: no matches (exit code 1 from grep).

- [ ] **Step 4: Commit**

```bash
git add docs/security/cryptography.md
git commit -s -m "$(cat <<'EOF'
docs(security): cryptographic primitives, key lifecycle, known limits

Adds docs/security/cryptography.md per M1 contract in
docs/security/README.md. Documents:
- Primitives in use (JWT HS256, Fernet, password hashing, CSPRNG)
- Key lifecycle for JWT_SECRET, master key (Fernet), gateway shared
  secret, and provider keys (env vs encrypted)
- Known limitations (HS256-only, no rotation overlap, Fernet vs AEAD,
  operator-managed TLS, no HSM/KMS adapter in M1)

Cross-references ADR 0010 (hot-reload), ADR 0011 (encrypted-at-rest
provider keys), and docs/security/encrypted-keys.md for operator
workflows.

Refs Phase E plan T6.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 7: `docs/security/audit-logging.md`

**Files:**
- Create: `docs/security/audit-logging.md`

**Background:**
The `audit_log` table is defined in `docs/db-schema.md` around line 790. Implementer must read that schema definition + grep `api/app/` for audit-write call sites to characterize what's actually logged.

- [ ] **Step 1: Survey audit-write sites**

Run:
```bash
cd /Users/kevinkeller/Desktop/lq-ai
sed -n '780,860p' docs/db-schema.md
grep -rn "audit_log\|AuditLog\|log_audit" api/app/ 2>&1 | head -20
```

Expected: see the schema definition + ≥10 call sites in `api/app/`.

- [ ] **Step 2: Author the doc**

Create `docs/security/audit-logging.md`:

```markdown
# Audit Logging

> **Scope:** what LQ.AI records to the audit log, retention, and integrity protection. Operators evaluating procurement responses often need this in writing; this is the operational reference for the `audit_log` table.

## What is logged

Each audit event is a row in the `audit_log` table (see [docs/db-schema.md §audit_log](../db-schema.md#audit_log) for the schema). Columns:

- `id` — surrogate primary key
- `actor_user_id` — who took the action (nullable for system-generated events)
- `event_type` — enumerated event kind (e.g. `matter.created`, `matter.archived`, `chat.sent`, `skill.invoked`, `file.uploaded`, `auth.password_changed`)
- `subject_type` + `subject_id` — what the action targeted (e.g. `project`, `chat`, `skill`)
- `details` — JSONB blob with event-specific context (request_id, prior + new values for state changes, IP if available)
- `created_at` — server-side timestamp (TIMESTAMPTZ)

Logged events at M1 include (verify against actual call sites — implementer should list every distinct `event_type` literal found in `api/app/`):

- **Authentication:** login success/failure, password change, session creation, session expiry, must-change-password gate satisfied
- **Matter lifecycle:** project create, update, archive, file attach/detach, skill attach/detach
- **Chat:** chat create, message send, skill invocation in a chat
- **Skill:** skill enable/disable, skill update
- **Admin:** user create, role change, password reset (admin-initiated)

## What is NOT logged

- Plaintext message content. Audit rows store `chat_id` + `event_type`, not the message body. Inference-routing has its own log (`inference_routing_log`) with provider/model/token-count, also without message content per PRD §4.
- Provider API responses. Same reasoning.
- Cryptographic material. JWT_SECRET, master keys, and provider keys are never logged.

## Retention

- **Default retention:** audit rows are never automatically deleted at M1. Operators with regulatory retention requirements (e.g. SOC 2 expects ≥1 year; some jurisdictions require longer) can rely on the default-retain posture.
- **Operator-controlled archival:** operators can `pg_dump --table=audit_log` to long-term storage on a schedule of their choosing. No first-class export workflow in M1; we may add one if operator demand surfaces.
- **Manual purge:** operators with privacy-driven purge requirements (e.g. GDPR right-to-erasure) can DELETE specific rows by `actor_user_id` directly. A future enhancement may add a `redact_user(user_id)` CLI command that NULLs the actor and PII-bearing `details` fields per user.

## Integrity protection

- **Application-layer:** the api process is the sole writer. The audit_log row inserts in the same transaction as the state-change it records, so an event is either both present in the audit log and reflected in the underlying tables, or neither.
- **Database-layer:** Postgres WAL provides crash-consistency. Operators with stricter requirements run Postgres with `synchronous_commit=on` (the default in our chart).
- **Tamper detection (not in M1):** chained hashes (each row commits a hash over `(prev_hash, current_row)`) would let operators detect after-the-fact tampering. Not in M1; tracked as DE-XXX (file via operator request — see PRD §9). Operators needing this today can use Postgres logical replication to a write-once destination.

## Operator workflows

### Investigating an incident

Pattern: pull all events for a given actor in a time window:

```sql
SELECT created_at, event_type, subject_type, subject_id, details
FROM audit_log
WHERE actor_user_id = '<uuid>'
  AND created_at BETWEEN '<from>' AND '<to>'
ORDER BY created_at DESC;
```

### Long-term archival

```bash
# Weekly archive
pg_dump -d lq_ai --table=audit_log --data-only --column-inserts \
  > audit-log-$(date +%Y-%m-%d).sql
```

### Compliance attestation

Operators answering "do you maintain an audit log of administrative actions" can reference this doc + the `audit_log` table schema in `docs/db-schema.md`. The Compliance Alignment Pack at `docs/compliance/` (separate cycle) maps specific audit events to specific SOC 2 / ISO 27001 controls.

## Cross-references

- [docs/db-schema.md §audit_log](../db-schema.md#audit_log) — schema definition.
- [docs/PRD.md §5 Security & Compliance](../PRD.md#5-security--compliance) — design intent.
- [docs/security/threat-model.md](threat-model.md) §Repudiation — threat coverage.
```

NOTE for implementer: replace "Logged events at M1 include" with the actual distinct `event_type` literals you found in Step 1. Don't invent event names.

- [ ] **Step 3: Commit**

```bash
git add docs/security/audit-logging.md
git commit -s -m "$(cat <<'EOF'
docs(security): audit-logging — what's logged, retention, integrity

Adds docs/security/audit-logging.md per M1 contract in
docs/security/README.md. Documents the audit_log table contract,
the event types written by api, what is intentionally NOT logged
(message content, provider responses, cryptographic material),
retention policy (default-retain; operator-controlled archive),
and integrity protection at app + DB layers.

Tamper-detection via chained hashes flagged as a deferred
enhancement; operators needing it today can use logical replication
to a write-once destination.

Refs Phase E plan T7.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 8: `docs/security/dependencies.md`

**Files:**
- Create: `docs/security/dependencies.md`
- Optionally create: `.github/dependabot.yml` (recommended)

**Background:**
Document the project's stance on dependency review, vulnerability monitoring, and update cadence. Per CLAUDE.md "Don't add libraries without justification" and PRD §7.5 supply-chain-transparency posture, the doc anchors three operational commitments: (1) SBOM ships with every release, (2) we run automated dependency scanning, (3) we have an update cadence operators can rely on.

Recommended to enable Dependabot at the same time so the doc isn't aspirational — it describes machinery that exists.

- [ ] **Step 1: Author the doc**

Create `docs/security/dependencies.md`:

```markdown
# Dependencies & Vulnerability Monitoring

> **Scope:** how LQ.AI manages its dependency tree, monitors for vulnerabilities, and ships updates. Pairs with the SBOM shipped with every release (see [docs/security/releases/README.md](releases/README.md)).

## Dependency review

Per [CLAUDE.md "Don't add libraries without justification"](../../CLAUDE.md#dont-add-libraries-without-justification), every new dependency added to `api/`, `gateway/`, or `web/` requires an explicit justification in the PR description. The bar is: "what does this give us that we couldn't reasonably build, and is the trade-off worth the SBOM entry?"

For dependencies touching:
- **Authentication / authorization / cryptography** — security-reviewer approval required per [.github/CODEOWNERS](../../.github/CODEOWNERS).
- **LLM-provider SDKs** — Inference Gateway boundary (PRD §4); same auto-routing.
- **Web frontend** — must not introduce React or other framework runtimes alongside SvelteKit; the boundary lives in [ADR 0009](../adr/0009-web-lq-ai-shell-coexistence.md).

## Automated scanning

Two layers of automated dependency-vulnerability scanning:

1. **GitHub Advisory Database / Dependabot.** `.github/dependabot.yml` configures weekly scans for `api/` (pip), `gateway/` (pip), `web/` (npm), and `.github/workflows/` (actions). High and critical advisories open PRs automatically.
2. **SBOM scanning.** The SBOM produced by the release workflow (per [docs/security/releases/README.md](releases/README.md)) is in SPDX JSON format and is parseable by any SCA tool. Operators evaluating a specific release can run `grype sbom:./api.spdx.json` (or equivalent) to check the dependency snapshot.

## Update cadence

| Severity | Response time |
|---|---|
| Critical | Patch released within 30 days |
| High | Patch released within 60 days |
| Medium | Folded into the next minor release |
| Low | Folded as convenient |

These mirror the vulnerability-fix commitments in [SECURITY.md](../../SECURITY.md). The cadence applies to both first-party fixes (LQ.AI code) and dependency advisories (upstream library fixes).

## Operator workflows

### Verifying a release's dependency tree

```bash
# Pull the SBOM from a release
gh attestation list --repo legalquants/lq-ai --type sbom <commit-sha>

# Or, from the registry directly (cosign attestation)
cosign download attestation \
  --predicate-type=https://spdx.dev/Document \
  ghcr.io/legalquants/lq-ai-api:vX.Y.Z \
  > api.spdx.json

# Scan with grype (or any SCA tool)
grype sbom:./api.spdx.json
```

### Pinning to a specific patch version

The Helm chart pins `image.tag` via values.yaml. Operators with strict change-management can pin to a specific tag and upgrade explicitly:

```bash
helm upgrade lq-ai ./deploy/helm/lq-ai \
  --set image.tag=v0.2.3 \
  -n lq-ai
```

## Known transitive risks

- **OpenWebUI fork.** `web/` is forked from OpenWebUI at the version pinned in [ADR 0001](../adr/0001-openwebui-fork-pin.md). Upstream advisories affect us; we track them and pull fixes per the cadence above. The fork pin means we don't auto-update with upstream master.
- **pgvector / Postgres.** Vector-index queries are powered by pgvector. Advisories against pgvector are uncommon (it's a thin C extension), but the Postgres major version (16 at M1) follows community LTS.

## Reporting a vulnerability in a dependency

If you find a vulnerability in a dependency that we ship, report it to the upstream project first; advise us via the channel in [SECURITY.md](../../SECURITY.md) so we can fast-track the bump if the advisory is severe enough.
```

- [ ] **Step 2: Optionally create dependabot.yml**

If the implementer is shipping this in the same commit (recommended), create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: /api
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    labels: ["dependencies", "api"]

  - package-ecosystem: pip
    directory: /gateway
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    labels: ["dependencies", "gateway"]

  - package-ecosystem: npm
    directory: /web
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    labels: ["dependencies", "web"]

  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: monthly
    labels: ["dependencies", "ci"]
```

- [ ] **Step 3: Commit**

```bash
git add docs/security/dependencies.md .github/dependabot.yml
git commit -s -m "$(cat <<'EOF'
docs(security): dependency review + vuln monitoring + update cadence

Adds docs/security/dependencies.md per M1 contract in
docs/security/README.md. Documents:
- Justification bar for new deps (per CLAUDE.md)
- Dependabot scanning (weekly for api/gateway/web pip+npm; monthly
  for actions)
- SBOM-based scanning operators can run on a specific release
- Update cadence aligned with SECURITY.md commitments
- Known transitive risks (OpenWebUI fork pin, pgvector)

Adds .github/dependabot.yml configuring the weekly scan schedule for
all four ecosystems (api pip, gateway pip, web npm, github-actions).

Refs Phase E plan T8.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 9: `docs/security/releases/README.md` (cosign verify walkthrough)

**Files:**
- Create: `docs/security/releases/README.md`

**Background:**
The verify command for keyless-signed images already appears in `docs/security/README.md`; we need the operator-facing detailed walkthrough that the README's "Detailed verification instructions land in `releases/README.md` at M1" pointer refers to.

- [ ] **Step 1: Author the doc**

Create `docs/security/releases/README.md`:

```markdown
# Release Verification

> **Scope:** how operators verify that a specific LQ.AI release's container images, SBOM, and SLSA provenance are authentic — i.e., that they were built by the LegalQuants release workflow and not tampered with in transit.

LQ.AI uses [sigstore keyless signing](https://docs.sigstore.dev/) (cosign + Fulcio + Rekor) and [SLSA build provenance](https://slsa.dev/spec/v1.0/) attestations.

## Quick verify (single image)

```bash
cosign verify \
  --certificate-identity-regexp "https://github.com/legalquants/lq-ai" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/legalquants/lq-ai-api:v0.1.0
```

A successful run prints the signing certificate's issuer, subject (the workflow OIDC identity), and Rekor transparency-log entry. Failure prints a diagnostic explaining whether the signature is missing, the cert doesn't match, or the cert's identity doesn't match the regexp.

## Verify all three images in a release

```bash
TAG=v0.1.0
for service in api gateway web; do
  echo "=== ${service} ==="
  cosign verify \
    --certificate-identity-regexp "https://github.com/legalquants/lq-ai" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    "ghcr.io/legalquants/lq-ai-${service}:${TAG}"
done
```

## Verify the SBOM attestation

The SBOM is bound to the image digest as a cosign attestation of type `spdxjson`:

```bash
cosign verify-attestation \
  --type spdxjson \
  --certificate-identity-regexp "https://github.com/legalquants/lq-ai" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/legalquants/lq-ai-api:v0.1.0 | jq -r '.payload' | base64 -d | jq '.predicate' > api.spdx.json

# Then scan the SBOM with your preferred tool
grype sbom:./api.spdx.json
```

## Verify the SLSA build provenance

SLSA provenance is attached via GitHub's attestations service. Verify with the `gh` CLI:

```bash
gh attestation verify \
  oci://ghcr.io/legalquants/lq-ai-api:v0.1.0 \
  --owner legalquants
```

A successful run prints the workflow path (`.github/workflows/release.yml`), the trigger event (tag push), and the input commit SHA — proving the image was built from that exact source by that exact workflow.

## What the verification proves

- **Image authenticity:** the signature was produced by a process holding a short-lived Fulcio cert bound to the LegalQuants workflow OIDC identity. An attacker who obtained access to the registry but not to the workflow's OIDC identity cannot produce a valid signature.
- **Image provenance:** the SLSA attestation pins the image to a specific commit SHA + workflow + builder. An attacker who modified the source after the fact cannot reproduce the attestation without re-running the workflow (which would produce a new, distinct attestation with a new timestamp).
- **Dependency snapshot:** the SBOM lists every dependency at build time. An attacker who substituted a dependency post-build cannot match the SBOM hash.

## What the verification does NOT prove

- The image is **free of vulnerabilities**. Verification proves authenticity, not safety. Operators run SCA tools against the SBOM independently.
- The release **was a deliberate choice by LegalQuants maintainers**. A compromised maintainer with the ability to push a tag could produce a valid release. This is the trust assumption shared by all OSS — see [SECURITY.md](../../../SECURITY.md) for the disclosure process if you suspect a compromised release.

## Operator-key signing (forks)

If you fork LQ.AI and prefer operator-controlled key signing (e.g., for air-gapped deployments where short-lived OIDC certs aren't available), replace the keyless flow in `.github/workflows/release.yml` step "Sign container image (keyless)" with:

```yaml
      - name: Sign container image (operator key)
        env:
          COSIGN_PRIVATE_KEY: ${{ secrets.COSIGN_PRIVATE_KEY }}
          COSIGN_PASSWORD: ${{ secrets.COSIGN_PASSWORD }}
        run: |
          cosign sign --yes --key env://COSIGN_PRIVATE_KEY \
            ghcr.io/your-org/lq-ai-${{ matrix.service }}:${{ steps.tag.outputs.tag }}
```

Then operators verify with:

```bash
cosign verify --key cosign.pub ghcr.io/your-org/lq-ai-api:v0.1.0
```

This trades keyless's ergonomic advantages for an operator-managed key lifecycle. For most public OSS deployments, keyless is the right default.

## Cross-references

- [docs/security/README.md](../README.md) — security-doc index.
- [docs/security/dependencies.md](../dependencies.md) — vulnerability monitoring.
- [.github/workflows/release.yml](../../../.github/workflows/release.yml) — the release workflow that produces these artifacts.
```

- [ ] **Step 2: Commit**

```bash
git add docs/security/releases/README.md
git commit -s -m "$(cat <<'EOF'
docs(security): cosign verify walkthrough for releases

Adds docs/security/releases/README.md per M1 contract in
docs/security/README.md (which already publishes the quick-verify
command and points to this file for the detailed walkthrough).

Covers:
- Quick verify (single image)
- Verify all three images in a release
- Verify SBOM attestation (cosign verify-attestation -> grype scan)
- Verify SLSA build provenance (gh attestation verify)
- What verification proves / does NOT prove
- Operator-key signing path for forks (air-gapped operators)

Refs Phase E plan T9.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 10: `SECURITY.md` GPG fix + `README.md` SLSA badge + `docs/security/README.md` status flip

**Files:**
- Modify: `SECURITY.md`
- Modify: `README.md`
- Modify: `docs/security/README.md`

**Background:**
Three small finishing items in one commit.

- [ ] **Step 1: Fix SECURITY.md GPG placeholder**

Edit `SECURITY.md`. Locate the line:

```
- **GPG key:** Available at [URL TBD — published before v1 release]
```

Replace with:

```
- **GPG key:** A GPG key for encrypted reports will be published before v1 release. Until then, please prefer GitHub Security Advisories (which encrypt in transit and at rest within GitHub's infrastructure).
```

- [ ] **Step 2: Add SLSA badge + security-docs link to README.md**

In `README.md`, add (near the top, beneath the title or current badges — verify the exact spot is consistent with existing badges):

```markdown
[![SLSA 3](https://slsa.dev/images/gh-badge-level3.svg)](https://slsa.dev) [![Security Policy](https://img.shields.io/badge/Security-Policy-blue)](./SECURITY.md)
```

Also add a short paragraph in the security/governance section (verify location — `## Security` or similar):

```markdown
LQ.AI ships with SLSA Level 3 build provenance, sigstore-signed
container images, and a Software Bill of Materials (SBOM) with every
release. See [`docs/security/`](docs/security/) for the threat model,
cryptography reference, audit-logging policy, and dependency-management
posture. Verify a release: [`docs/security/releases/README.md`](docs/security/releases/README.md).
```

- [ ] **Step 3: Flip status entries in docs/security/README.md**

In `docs/security/README.md`, update the status column for the rows we just shipped:

| Artifact | New status |
|---|---|
| `sbom.spdx.json` | Landed (Phase E) |
| `releases/` (signed attestations) | Landed (Phase E) |
| `slsa/` (provenance) | Landed (Phase E) |
| `threat-model.md` | Landed |
| `dependencies.md` | Landed |
| `cryptography.md` | Landed |
| `audit-logging.md` | Landed |

Locate the table around the top of the file and change `M1` → `Landed (Phase E)` for the supply-chain rows and `Landed` for the doc rows.

- [ ] **Step 4: Verify links resolve**

Run:
```bash
cd /Users/kevinkeller/Desktop/lq-ai
for f in docs/security/threat-model.md docs/security/dependencies.md \
         docs/security/cryptography.md docs/security/audit-logging.md \
         docs/security/releases/README.md; do
  test -f "$f" && echo "OK $f" || echo "MISSING $f"
done
grep -c "URL TBD" SECURITY.md
grep -c "slsa.dev" README.md
```

Expected: 5 × `OK ...`. SECURITY.md `URL TBD` count = 0. README.md `slsa.dev` count ≥ 1.

- [ ] **Step 5: Commit**

```bash
git add SECURITY.md README.md docs/security/README.md
git commit -s -m "$(cat <<'EOF'
docs: SECURITY.md GPG placeholder + README SLSA badge + security
status table

Three finishing items for Phase E:
- SECURITY.md: replace "[URL TBD]" GPG placeholder with explicit
  guidance to use GitHub Security Advisories until v1
- README.md: add SLSA Level 3 badge + Security Policy badge + a
  short paragraph linking to docs/security/
- docs/security/README.md: flip status column from "M1" to "Landed"
  (or "Landed (Phase E)") for the artifacts shipped by this phase

Refs Phase E plan T10.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 11: Final verification — dry-run the release workflow

**Files:**
- None modified. Verification only.

**Background:**
Trigger the release workflow with `workflow_dispatch` + `dry_run=true` to confirm the build matrix succeeds end-to-end. The dry-run skips push and sign steps but exercises the SBOM step and the Docker build. A real release happens only when Kevin tags a version.

- [ ] **Step 1: Trigger dry-run**

Run (requires `gh` CLI authenticated to the repo):

```bash
cd /Users/kevinkeller/Desktop/lq-ai
gh workflow run release.yml -f dry_run=true
sleep 5
gh run list --workflow=release.yml --limit 1
```

Expected: a run is queued; `gh run list` shows it as `queued` or `in_progress`.

- [ ] **Step 2: Watch the run**

Run:
```bash
gh run watch
```

Expected: matrix jobs (build-and-push for api/gateway/web) complete with status `success`. The `sbom` and `sign` jobs are SKIPPED in dry-run because their job-level `if:` gates evaluate to false (consistent with the dry-run semantic of "verify the build works without the supply-chain side-effects"). Final status: success (with sbom + sign jobs marked "skipped").

- [ ] **Step 3: Spot-check SBOM via the local Makefile target**

The release workflow's SBOM job is gated out of dry-run, so artifact-download spot-check is not available without a real tag push (which is Kevin's call to make). Instead, exercise the local SBOM tooling against the source tree:

```bash
cd /Users/kevinkeller/Desktop/lq-ai
make sbom
ls -la artifacts/sbom/
jq -r '.spdxVersion, (.packages | length)' artifacts/sbom/api.spdx.json
```

Expected: `artifacts/sbom/{api,gateway,web}.spdx.json` exist, each non-empty, packages count > 0. This is a SOURCE-TREE SBOM (slightly different from the IMAGE SBOM the release workflow ships) but exercises the same Syft toolchain and proves the upstream tooling works. End-to-end image-SBOM verification happens at the first real release tag.

- [ ] **Step 4: Cleanup local artifacts + write completion note**

Run:
```bash
rm -rf artifacts/sbom
```
(the source-tree SBOMs are throwaway; the artifacts/ directory is gitignored or should be — verify with `git status` showing nothing).

Then update `docs/M1-PROGRESS.md` if it tracks backend phases (verify first):

```bash
grep -i "phase e\|release.readiness" docs/M1-PROGRESS.md 2>&1 | head -5
```

If there's a Phase E entry, mark it complete. If the file doesn't track phases this way, skip.

- [ ] **Step 5: Final commit (if M1-PROGRESS.md updated)**

```bash
git add docs/M1-PROGRESS.md
git commit -s -m "$(cat <<'EOF'
docs: Phase E (release readiness) complete

All 5 handoff workstreams + 3 extra M1 docs from
docs/security/README.md shipped. Release workflow dry-run verified
on workflow_dispatch (run ID <fill>). Tag-and-publish is gated on
maintainer action.

Refs Phase E plan T11.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

If `M1-PROGRESS.md` doesn't track phases this way, skip Step 5.

---

## Plan completion criteria

Phase E is done when:

1. `.github/workflows/release.yml` exists, lints, and runs cleanly on `workflow_dispatch` with `dry_run=true` (matrix builds api/gateway/web + SBOM generates + sign job is skipped).
2. `deploy/helm/lq-ai/` exists; `make helm-lint` passes; `make helm-template` renders ≥14 resources against `values-example.yaml`.
3. `docs/security/threat-model.md`, `cryptography.md`, `audit-logging.md`, `dependencies.md`, `releases/README.md` all exist with no `[fill: ...]` markers.
4. `SECURITY.md` has no `URL TBD` placeholder.
5. `README.md` has a SLSA badge and a link to `docs/security/`.
6. `docs/security/README.md` status table reflects the new shipped state.
7. Every commit is `-s` signed, has the Co-Author trailer, and is pushed to `kk/main/Frontend_Design`.

## Open items routed forward (not in Phase E)

- Tagging an actual release (`v0.1.0` or similar). Kevin decides when.
- Compliance Alignment Pack (`docs/compliance/`) mapping to SOC 2 / ISO 27001 / ISO 42001 / GDPR / HIPAA / FedRAMP. Separate cycle.
- PR-validation CI workflow (test/lint/typecheck on every PR). Separate cycle.
- Wave D feature work (Knowledge browser, KB-attach loop, outputs panel, Saved Prompts, Receipts mode, Citation Engine UI).
- Wave F V2-FALLBACK cleanup (5 items from Wave B v2).
- Operator-key cosign signing as a first-class chart values switch (Phase E ships keyless only; operator-key is documented as a fork workflow).
- Chained-hash audit-log integrity protection (DE-XXX candidate per `audit-logging.md`).
