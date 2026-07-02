"""Drift guard for the production edge Caddyfile (SAAS-2, ADR-F059 D4).

Asserts the security-gate stanzas are present in deploy/caddy/Caddyfile. This is
a DRIFT GUARD, not a syntax check (that is `caddy validate`, run in CI/manually):
if a refactor drops the internal-deny or the access_token scrub, this fails.

SKIPPED when the file is absent — a containerized api test run may not mount
deploy/. CI's full checkout enforces it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_CADDYFILE = Path(__file__).resolve().parents[2] / "deploy" / "caddy" / "Caddyfile"

pytestmark = pytest.mark.skipif(
    not _CADDYFILE.is_file(),
    reason="deploy/caddy/Caddyfile not present in this checkout (drift guard skipped)",
)


@pytest.mark.unit
def test_caddyfile_denies_internal_wopi_and_metrics() -> None:
    text = _CADDYFILE.read_text(encoding="utf-8")
    # Named `path` matchers deny both the bare prefix and the wildcard.
    assert "@internal path /api/v1/internal /api/v1/internal/*" in text
    assert "@wopi path /api/v1/wopi /api/v1/wopi/*" in text
    assert "@metrics path /metrics /metrics/*" in text
    assert "handle @internal" in text
    assert "handle @wopi" in text
    assert "handle @metrics" in text
    # All three denies are uniform 404s (never 403 — no existence leak).
    assert text.count("respond 404") >= 3


@pytest.mark.unit
def test_caddyfile_sets_security_headers() -> None:
    text = _CADDYFILE.read_text(encoding="utf-8")
    assert "Strict-Transport-Security" in text
    assert "X-Content-Type-Options" in text
    assert "Referrer-Policy" in text
    assert "Content-Security-Policy-Report-Only" in text
    assert "frame-ancestors 'self'" in text


@pytest.mark.unit
def test_caddyfile_scrubs_access_token_from_logs() -> None:
    text = _CADDYFILE.read_text(encoding="utf-8")
    assert "replace access_token REDACTED" in text


@pytest.mark.unit
def test_caddyfile_routes_api_and_streams() -> None:
    text = _CADDYFILE.read_text(encoding="utf-8")
    assert "reverse_proxy api:8000" in text
    assert "reverse_proxy web:8080" in text
    assert "flush_interval -1" in text  # SSE
