# Adeu pinning + supply-chain verification (C-R0)

**Slice:** C-R0 (research spike — no code, no `pyproject` change). **Gates:** C4 (`apply_redline` tool).
**Status:** verified 2026-06-21 against the live PyPI release + an isolated container install.
**Decision input for:** ADR-F031 (Adeu redline tool). Adeu is *confirmed working + MIT* by the maintainer
(decision A) — this is **not** a go/no-go; it pins the version, the SDK surface, the egress posture and the
license chain so C4 builds against a frozen, audited target.

> **Do not add Adeu to `api/pyproject.toml` yet.** That is C4. This doc records *what* C4 will pin and
> *why it is safe*.

---

## 1. Decision summary

| Question | Answer | Evidence |
|---|---|---|
| Pin | **`adeu==1.12.1`** (latest stable, 2026-06-21) | PyPI `info.version` |
| License (the package) | **MIT** (Dealfluence Oy, © 2026) | PyPI metadata + `License :: OSI Approved :: MIT License` classifier |
| Python | **requires `>=3.12`** — our api/worker runtime is 3.12 ✓ | `requires_python` field; dev image is py3.12 |
| SDK we use | `RedlineEngine`, `ModifyText` (+ `AcceptChange`/`RejectChange`/`ReplyComment`), `process_batch(..., dry_run=)` | introspected on 1.12.1 (§3) |
| Egress | **Zero.** SDK path loads no network/server modules; a real redline ran with the network namespace removed | `--network=none` smoke (§4) |
| New copyleft introduced | **None.** Whole transitive tree is permissive except `certifi` (MPL-2.0, weak/file-level) — **already in our tree** via `httpx` | `pip-licenses` scan (§5) + existing-tree check |
| Real cost | **SBOM bloat**: `fastmcp[apps]` is a *hard* runtime dep → ~80 packages installed (a web server + credential-store libs) we never run | `requires_dist` + full freeze (§6) |

**Verdict:** Adeu is safe to pin at `1.12.1` for C4. It satisfies rule B (no *new* copyleft) and the
gateway-only-egress rule (SDK is pure-local, proven offline). The one genuine trade-off — installing the
unused FastMCP server tree — is all-permissive and **runtime-isolated** (never imported), but it is a real
supply-chain surface; §6 records the C4 decision and the mitigation.

> **Confirmed integration decision (maintainer, 2026-06-21):** integrate via the **Python SDK in-process**
> (face #1), *not* via Adeu's MCP server. Rationale: C4's value is a mandatory **code-side surgical gate**
> (validated-write, ADR-F018) — our code must sit between the agent's proposal and the applied edit, which an
> in-process call gives for free; routing Adeu (a *local, zero-network* tool) through MCP would add a
> client+server+transport and still need our validator interposed. **MCP-as-a-capability is a separate,
> approved milestone** (sanction-sync of upstream's gateway-brokered MCP client) — see the COMM plan /
> MILESTONES. **Hard requirement attached to this decision: new Adeu versions must drop in *easily*** — see
> §8 Upgrade process.

---

## 2. Version pin

- **Pin: `adeu==1.12.1`.** Latest stable on PyPI as of 2026-06-21.
- `AI_CONTEXT.md` / docs referenced elsewhere are **stale at v1.6.0** — do not trust the doc API; trust the
  introspected 1.12.1 surface in §3.
- Release history is long and active (v0.0.1 → v1.12.1; the maintainer ships frequently), confirming the
  brief's "actively maintained — pull new versions". C4 pins exactly and bumps deliberately (each bump is an
  SBOM diff + a re-run of the §4 egress smoke + the §3 signature check, because the SDK is young and may
  change shape).
- **Compatibility:** `requires_python >=3.12`; the api and arq/ingest workers run Python 3.12, so this is a
  non-issue. (The dev *host* is 3.11 — irrelevant; Adeu runs in the container.)

---

## 3. SDK surface (verified on 1.12.1)

Top-level exports (`dir(adeu)`):
`AcceptChange, DocumentChange, ModifyText, RedlineEngine, RejectChange, ReplyComment,
apply_edits_to_markdown, diff, domain, extract_text_from_stream, ingest, markup, models, redline, utils,
version`.

The three the plan named, with **actual signatures on 1.12.1**:

```python
# adeu/redline/engine.py:210
class RedlineEngine(doc_stream: io.BytesIO, author: str = "Adeu AI")

# adeu/models.py:17  (a pydantic BaseModel)
class ModifyText(*, type: Literal["modify"] = "modify",
                 target_text: str, new_text: str, comment: Optional[str] = None)

# adeu/redline/engine.py:1309  (method on RedlineEngine)
def process_batch(self, changes: List[DocumentChange], dry_run: bool = False) -> dict
```

`process_batch(..., dry_run=True)` returns a `dict` with keys:
`actions_applied, actions_skipped, edits_applied, edits_skipped, skipped_details, edits, engine, version`.

**Why this maps cleanly onto the C4 design:**
- `ModifyText.target_text` + `new_text` are exactly the two strings the **surgical gate** compares
  (per-edit diff-ratio / token-span — see `commercial-lawyer-method.md`). The model proposes narrow
  find/replace edits; it never authors OOXML.
- `ModifyText.comment` carries the **mandatory per-edit rationale**; Adeu renders it as a native Word
  comment (observed in the smoke log: `Adding comment author='LQ.AI Commercial'`).
- `process_batch(dry_run=True)` is the **mandatory self-review preview** the plan asked for — native, not
  bolted on. C4 calls `dry_run=True` first, the gate inspects `result["edits"]` / `skipped_details`, then a
  second `dry_run=False` call commits to the `.docx`.
- `AcceptChange` / `RejectChange` / `ReplyComment` are first-class → they are the **accept/reject/counter**
  verbs C5 (negotiation rounds) needs against an incoming counterparty-marked `.docx`. (C5 detail, recorded
  here so it isn't re-discovered.)

> **Use the SDK, never the server.** `adeu/server.py` and `adeu/mcp_components/*` are a bundled FastMCP
> server. We do **not** import them (a second egress; ADR-F010). C4 imports only the symbols above.
> `langchain-adeu` (a WIP toolkit) is **not** on PyPI — do not use it.

---

## 4. Egress safety — proven, not asserted

Two independent checks, both clean:

**(a) Source scan.** The only network-capable imports in Adeu's own source (`urllib`) live exclusively in
the server path — `adeu/mcp_components/{desktop_auth,tools/auth,tools/email,tools/validation}.py`. The
redline engine (`adeu/redline/engine.py`), `models.py`, `diff`, `markup` have **none**. Every `fastmcp`
reference is in `server.py` + `mcp_components/*`.

**(b) Runtime isolation + offline execution.** `import adeu; from adeu import RedlineEngine, ModifyText`
loaded **none** of `fastmcp, fastmcp_slim, mcp, uvicorn, starlette, sse_starlette, keyring, secretstorage,
jeepney, websockets, authlib, cryptography, adeu.server, adeu.mcp_components, requests, httpx, httpcore,
urllib3, aiohttp` (checked via `sys.modules`). Then a real `ModifyText` redline ran through
`process_batch(dry_run=True)` inside a container started with **`--network=none`** (no network namespace at
all) → succeeded, returned the expected `dict`, and *still* loaded none of those modules afterward.

> Conclusion: importing the SDK does not drag in the server/network tree, and the redline path needs no
> network. C4 wraps it behind `guarded_dispatch` with a `COMMERCIAL_AREA_KEY` grant; Adeu adds **no** new
> egress and does not breach the gateway-only rule. Pure byte→OOXML.

---

## 5. License chain — all permissive; no *new* copyleft

Full transitive tree (`pip-licenses` over the complete install of `adeu==1.12.1`) is permissive
— **Apache-2.0 / BSD-2/3-Clause / MIT / ISC / PSF-2.0 / Unlicense** — with a **single** exception:

| Package | Version | License | Note |
|---|---|---|---|
| **`certifi`** | 2026.6.17 | **MPL-2.0** | Weak, **file-level** copyleft. Mozilla's CA-cert bundle. Pulled transitively (`httpx → certifi`). |

Adeu's **direct** runtime deps are all permissive: `diff-match-patch` (Apache-2.0), `fastmcp[apps]`
(Apache-2.0), `jinja2` (BSD), `keyring` (MIT), `lxml` (BSD-3-Clause), `pydantic` (MIT), `python-docx`
(MIT), `rapidfuzz` (MIT), `structlog` (MIT/Apache-2.0). (`pywin32` is `sys_platform=="win32"` only —
excluded on our Linux runtime.)

**Rule-B verdict (no copyleft in new dependencies):**
- The only copyleft item is `certifi` (MPL-2.0), and it is **already in our dependency tree** —
  `lq-ai-api-dev:latest` ships `certifi 2026.05.20`, pulled by our existing direct dep `httpx>=0.27,<0.29`.
  **Adeu introduces no new copyleft.**
- MPL-2.0 is *weak, file-level* copyleft: the obligation is only to share modifications **to certifi's own
  files**, which we never modify. It imposes nothing on our code and is incomparably weaker than the
  PyMuPDF **AGPL** open question. No action required beyond noting it in `NOTICES.md` at C4 (it is likely
  already covered transitively).

---

## 6. The real trade-off: SBOM bloat from `fastmcp[apps]`

`fastmcp[apps]>=3.1.1` is in Adeu's `requires_dist` as a **hard runtime dependency, not an extra**. So
`pip install adeu` pulls the *entire* MCP-server stack we never run — ~80 packages, including a web server
(`uvicorn`, `starlette`, `sse-starlette`, `websockets`), credential-store libs (`keyring`,
`SecretStorage`, `jeepney`, `py-key-value-aio`), `cryptography`, `Authlib`, `opentelemetry-api`,
`watchfiles`, `mcp`, `fastmcp-slim`. All permissive — but a large supply-chain surface for a tool we use
only to write tracked changes into a `.docx`.

**This is a genuine C4 decision.** Options, in order of preference:

1. **Accept the tree, isolate at runtime + lock it.** All-permissive; §4 proves the server libs are never
   imported by the redline path, so runtime attack surface ≈ the SDK only. C4 pins the **full transitive
   set** in the lockfile (so the SBOM is explicit and reviewable) and adds an import guard / test asserting
   `adeu.server` and `adeu.mcp_components` are never imported in our process. **Recommended.**
2. **Pursue an SDK-only install.** A `fastmcp-slim` package already exists in the tree — investigate
   whether Adeu exposes (or upstream would add, per maintainer's existing relationship) an extra that
   installs the redline SDK *without* `fastmcp[apps]`. Best long-term; not blocking C4.
3. Vendor only the redline modules — **rejected** (forks the dep, defeats "pull new versions", maintenance
   debt).

**Recorded as a C4 risk + an open item** (see `COMM-…-decomposition.md` § Open questions): the SBOM bloat
is the price of Adeu; the mitigation is lockfile pinning + proven import isolation.

---

## 7. Reproduction

All commands run in throwaway containers — nothing installed on the host, nothing mounted from the project,
nothing added to `pyproject`.

```bash
# (a) version + license + direct deps, straight from PyPI metadata
python3 -c 'import json,urllib.request; d=json.load(urllib.request.urlopen("https://pypi.org/pypi/adeu/json")); \
  print(d["info"]["version"], d["info"]["license"][:11]); print(d["info"]["requires_dist"])'

# (b) full transitive license tree
docker run --rm python:3.12-slim bash -c \
  'pip install -q "adeu==1.12.1" pip-licenses && pip-licenses --format=plain --order=license'

# (c) SDK signatures + source-level network-import scan  (script: /tmp/adeu_check.py in the slice)
docker run --rm -v /tmp/adeu_check.py:/c.py:ro python:3.12-slim bash -c 'pip install -q "adeu==1.12.1" && python /c.py'

# (d) OFFLINE redline smoke — install with network, run with the network namespace removed
cid=$(docker run -d python:3.12-slim sleep 900)
docker exec "$cid" pip install -q "adeu==1.12.1"; docker commit "$cid" adeu-throwaway:cr0; docker rm -f "$cid"
docker run --rm --network=none -v /tmp/adeu_smoke.py:/s.py:ro adeu-throwaway:cr0 python /s.py
docker rmi adeu-throwaway:cr0
```

Observed `(d)` output: `server/network modules loaded: NONE` (before and after) and
`process_batch(dry_run=True) -> dict [...'edits_applied'...'edits'...]` → **SMOKE OK**.

---

## 8. Hand-off to C4 (non-binding pointers)

- Pin `adeu==1.12.1`; pin the **full transitive set** in the lockfile; record the tree + the MPL-2.0
  certifi note in `NOTICES.md`.
- Inject the engine via DI (no import-time instantiation; wire in arq worker `on_startup` **and** API
  lifespan) — matches the codebase DI rule and ADR-F031's verification.
- Tool contract: model proposes `List[ModifyText]` (each with `target_text`/`new_text`/`comment`); the
  `*Input` validator enforces the **surgical thresholds** from `commercial-lawyer-method.md`
  (reject-don't-sanitize); `process_batch(dry_run=True)` previews → gate inspects → `dry_run=False` commits.
- Add a test asserting `adeu.server` / `adeu.mcp_components` are never imported in our process (egress
  guard), and a round-trip test that reopens the redlined `.docx` and asserts `w:ins`/`w:del` carry
  author/date.

### 8.1 Upgrade process — bumping Adeu must stay trivial (maintainer hard rule)

Adeu ships frequently and the SDK surface is young, so C4 must make version bumps a **one-line change +
re-run the same verifications**, never a refactor:

1. **Adapter seam.** Wrap Adeu behind a single thin adapter (`commercial_tools.py` → a `RedlineEngine`
   wrapper). Our code references *our* adapter's stable interface, never Adeu symbols scattered across the
   codebase — so an SDK shape change touches **one file**.
2. **Single pin.** The version lives in exactly one place (`api/pyproject.toml`); the full transitive set is
   pinned in the lockfile. A bump = change the pin + relock.
3. **Re-verify on every bump (CI regression tests, ported from this spike):**
   - the **signature check** (§3) — assert `RedlineEngine`/`ModifyText`/`process_batch` still have the
     expected shape (a contract test; fails loudly if upstream renames/moves a symbol);
   - the **egress smoke** (§4) — `import adeu` loads none of the server/network markers, and a `dry_run`
     redline runs offline;
   - the **license scan** (§5) — the transitive tree introduces no new copyleft beyond the in-tree
     `certifi`/MPL-2.0;
   - the **round-trip** redline test (Accept/Reject yields expected text).
4. **Bump is mechanical:** if 1–3 stay green, merge the bump; if the signature check fails, the breakage is
   localised to the adapter (step 1). Keep these as fast tests so "pull the new Adeu" is a routine PR.

## 9. Open items (carried to the plan)

1. **MPL-2.0 `certifi`** — already in-tree via `httpx`; record in `NOTICES.md`. (Distinct from, and far
   weaker than, the PyMuPDF AGPL open question.)
2. **`fastmcp[apps]` SBOM bloat** — accept-and-isolate (§6 option 1) vs. pursue an SDK-only extra
   (option 2). Decide at C4.
