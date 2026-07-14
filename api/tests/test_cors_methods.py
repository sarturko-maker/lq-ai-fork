"""Regression: CORS must advertise every HTTP verb the API actually serves.

VM UAT bug (2026-07-14): saving House Brief (PUT /organization-profile) and
Branding (PUT /branding) failed in the browser with "Failed to fetch", while
chats (POST) worked. Root cause: `CORS_ALLOW_METHODS` in `app.main` listed
GET/POST/PATCH/DELETE/OPTIONS but not PUT, so the cross-origin preflight for a
PUT was rejected with a 400 and the browser never issued the request.

These tests pin PUT (and the whole verb set) against the real CORSMiddleware
behaviour and against the verbs the router actually mounts, so dropping a verb
that a live endpoint needs breaks CI instead of a user's save button.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.main import CORS_ALLOW_METHODS, app

_ORIGIN = "http://localhost:3000"


def _preflight_client() -> TestClient:
    """A throwaway app wired with the SAME allow-methods the real app uses."""
    probe = FastAPI()
    probe.add_middleware(
        CORSMiddleware,
        allow_origins=[_ORIGIN],
        allow_credentials=True,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

    @probe.put("/thing")
    async def _put_thing() -> dict[str, bool]:  # pragma: no cover - body trivial
        return {"ok": True}

    return TestClient(probe)


def test_put_preflight_is_allowed() -> None:
    """A cross-origin PUT preflight must succeed and advertise PUT."""
    client = _preflight_client()
    resp = client.options(
        "/thing",
        headers={
            "Origin": _ORIGIN,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert "PUT" in resp.headers["access-control-allow-methods"]


def test_all_served_verbs_are_in_the_allowlist() -> None:
    """Every HTTP verb mounted on the real app must be CORS-allowlisted.

    Catches the class of bug directly: add a PUT/other-verb endpoint but forget
    to allowlist the verb, and a cross-origin browser call silently 400s at the
    preflight. HEAD is auto-added by Starlette for GET routes; OPTIONS is the
    preflight verb itself — both are covered by GET/OPTIONS being present.
    """
    served: set[str] = set()
    for route in app.routes:
        served |= set(getattr(route, "methods", set()) or set())
    served -= {"HEAD"}  # implicit companion of GET
    missing = served - set(CORS_ALLOW_METHODS)
    assert not missing, f"verbs served but not CORS-allowlisted: {sorted(missing)}"
