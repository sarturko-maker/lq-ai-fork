# ADR 0003 — Error handling: parallel `lq_ai.errors` packages with an OpenAPI-defined contract

**Status:** Accepted (2026-05-08)
**Decision-makers:** Kevin Keller (initial maintainer)
**Affected components:** `api/`, `gateway/`, `tests/` (cross-subsystem conformance)
**Related:** [ADR 0002 — Backend-owned auth](0002-backend-owned-auth.md), [docs/M1-PROGRESS.md "Deferred to B5"](../M1-PROGRESS.md), [CONTRIBUTING.md "Code style → Exceptions"](../../CONTRIBUTING.md#python-api-gateway-scripts)

---

## Context

`CONTRIBUTING.md` has carried — since A1 — the line *"use the project's `lq_ai.errors` exception hierarchy; do not raise bare `Exception`"*. The package was never actually built. B1 and B3 each surfaced the absence in their reports; B5 is the natural landing spot because B5 is the first task where backend↔gateway error semantics need to align (every gateway error becomes a backend error of some shape).

The **deferred-items table** in [`docs/M1-PROGRESS.md`](../M1-PROGRESS.md) describes the package as living "in a shared module that both `api/` and `gateway/` import from." Read literally, this contradicts [`CLAUDE.md`](../../CLAUDE.md):

> Each subsystem (`api/`, `gateway/`, `web/`) is a self-contained service. They talk over HTTP using OpenAPI-defined contracts. **There is no shared in-process code** — adapters cross the boundary explicitly.

The two statements can be reconciled three ways:

- **Option A — Shared Python distribution.** Put the hierarchy in `packages/lq-ai-errors/` with its own `pyproject.toml`; install it as an editable dependency in both `api/` and `gateway/`. *Honors the deferred-items hypothesis but violates CLAUDE.md's hard rule on shared in-process code.*
- **Option B — Parallel hierarchies + OpenAPI-defined contract.** Each subsystem owns its own `app.errors` Python package with the same canonical error-code enum and the same exception-to-HTTP mapping. The shared artifact is the **error-code enum + structured error-body schema in the OpenAPI sketches** (`docs/api/backend-openapi.yaml`, `docs/api/gateway-openapi.yaml`). A cross-subsystem conformance test under `tests/` verifies the two enums stay in sync. *Honors CLAUDE.md's hard rule and matches how the rest of the system already works (api/ and gateway/ communicate over HTTP, not via shared imports).*
- **Option C — Single subsystem only.** Accept the inconsistency that gateway has its own (already-existing) `ProviderAdapterError` hierarchy and let `api/` invent its own. *Already the de-facto state; the cost is architectural drift over time and no enforcement that the two error vocabularies line up.*

## Decision

**Adopt Option B.** Each subsystem ships its own `app.errors` Python package; the contract that ties them together is documented in the OpenAPI sketches and verified by a cross-subsystem conformance test.

Concretely:

- **`api/app/errors.py`** — backend exception hierarchy. `LQAIError(code, message, http_status, details)` base; subclasses for the codes the backend emits (`unauthorized`, `forbidden`, `not_found`, `validation_error`, `rate_limited`, `internal_error`, `password_change_required`, `gateway_unreachable`, `gateway_timeout`, `gateway_invalid_response`, `provider_unavailable`, `tier_below_minimum`). FastAPI exception handler in `api/app/main.py` translates these to the response shape `{"detail": {"code": ..., "message": ..., "details": ...}}` documented in `docs/api/backend-openapi.yaml` as the `Error` schema.

- **`gateway/app/errors.py`** — gateway exception hierarchy. Same base class shape, codes from the gateway-openapi `GatewayError.code` enum (`tier_below_minimum`, `tier_disallowed_globally`, `anonymization_failed`, `invalid_model`, `provider_unavailable`, `rate_limit_exceeded`, `invalid_request`, `not_implemented`, `unauthorized`). FastAPI exception handler translates to the response shape `{"error": {"code": ..., "message": ..., "details": ...}}` per the existing `GatewayError` schema. The gateway's existing `ProviderAdapterError` hierarchy in `gateway/app/providers/base.py` continues to exist for adapter-internal errors and is mapped to `LQAIError` subclasses at the route boundary; B5 does not refactor adapters.

- **OpenAPI sketches** — the canonical contract. `docs/api/backend-openapi.yaml` gains an explicit `Error` schema (it was missing — a real gap). `docs/api/gateway-openapi.yaml`'s `GatewayError` is already canonical and does not change.

- **Cross-subsystem conformance test** — `tests/test_error_code_contract.py` imports both subsystems' code enums and asserts: (1) every code an `api/` exception emits that originates from the gateway is also a code the gateway side declares, (2) the canonical messages defined for shared codes match. This is the binding contract; it lives in the cross-cutting `tests/` directory per CLAUDE.md.

The two response **wrapper shapes are deliberately different**: backend uses `{"detail": ...}` (matches FastAPI's native `HTTPException` response, matches the B2 forced-password-change pattern, matches what the OpenWebUI fork's auth-delegation glue already needs to read), and gateway uses `{"error": ...}` (matches the existing `GatewayError` schema, matches the gateway adapter tests that already assert on `body["error"]["code"]`). The **inner shape is identical** (`code` + `message` + `details`) and is what the cross-subsystem code enum actually constrains. We do not unify the wrappers because doing so would either (a) churn the gateway's shipped tests and OpenAPI without value, or (b) push a non-FastAPI-native shape onto the backend. The wrapper difference is documented in both OpenAPI sketches.

The pre-existing **A4 `_stub.not_implemented` 501 envelope** uses `{"error": {"code": "not_implemented", ...}}` for stub endpoints. Since the stubs are transitional (each one is replaced as its task lands) and since 47 stub-conformance tests assert on the existing `body["error"]` shape, the stub envelope **stays as-is** until each stub is replaced by a real handler. New typed errors raised from real handlers go through the `lq_ai.errors` hierarchy and produce the canonical `{"detail": {...}}` shape.

## Consequences

**Positive:**

- Honors CLAUDE.md's hard rule on subsystem isolation. No shared Python distribution, no shared imports across `api/` and `gateway/`.
- The contract that matters (the error-code vocabulary) is anchored in the same artifact that already governs cross-subsystem semantics — the OpenAPI sketches.
- Each subsystem's exception hierarchy can evolve independently for codes that don't cross the boundary (e.g., `password_change_required` is backend-only; `tier_below_minimum` is gateway-only and propagates through the backend as a passthrough).
- The cross-subsystem conformance test makes drift loud rather than silent.

**Negative:**

- Two parallel implementations of the base class and the FastAPI exception handler. The duplication is small (~50 lines per subsystem) and the conformance test catches divergence on the values that actually matter; this is a tolerable cost.
- Operators reading both OpenAPI sketches see two different wrapper keys (`detail` vs. `error`). Documented in both sketches; not a usability hazard at the level of programmatic clients (each client calls one of the two services).

**Mitigations:**

- The conformance test under `tests/` is the load-bearing artifact. If a code-name appears in one subsystem and not the other, the test fails.
- If a future task argues for a single Python package (e.g., M3 introduces a Word add-in service that needs shared exceptions), this ADR is reopened. Until then, the cost-benefit is clearly on Option B's side.

## Implementation notes

- B5 lands the package in both subsystems plus the conformance test.
- Existing `HTTPException(detail="string")` raises in `api/app/api/auth.py` are *not* mass-rewritten in B5; they are mapped at handler-level only when B5 touches that handler for other reasons. Per CLAUDE.md "don't churn the codebase for the sake of it."
- New code raises `LQAIError` subclasses directly. The exception handler does the translation.
- The 501 stub helper (`api/app/api/_stub.py::not_implemented`, `gateway/app/api/inference.py::_not_implemented`) is unchanged.

---

*Updates to `docs/M1-PROGRESS.md` reflect that this is the chosen path and that the "lives in a shared module" phrasing in the deferred-items table was a hypothesis, not a directive.*
