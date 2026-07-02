"""Unit tests for the auth rate limiter (SAAS-2, ADR-F059).

Exercises the limiter through its injectable backend seam with a hand-rolled
in-memory fake (no fakeredis dependency) and a driven clock (no sleeps):
window math, per-IP vs per-account key separation, fail-open on a backend
fault, identifier normalisation, and that no raw identifier lands in a key.
"""

from __future__ import annotations

import types

import pytest

from app.config import Settings
from app.security.rate_limit import (
    RateLimiter,
    RateLimitRule,
    _hash_identifier,
    get_rate_limiter,
)


class _Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeRateLimitBackend:
    """In-memory fixed-window backend with a driven clock (test double)."""

    def __init__(self, clock: _Clock) -> None:
        self._clock = clock
        self.store: dict[str, tuple[int, float]] = {}

    async def incr_with_expiry(self, key: str, window_seconds: int) -> tuple[int, int]:
        now = self._clock()
        count, expiry = self.store.get(key, (0, 0.0))
        if now >= expiry:
            count = 0
            expiry = now + window_seconds
        count += 1
        self.store[key] = (count, expiry)
        return count, max(0, round(expiry - now))


class RaisingBackend:
    async def incr_with_expiry(self, key: str, window_seconds: int) -> tuple[int, int]:
        raise RuntimeError("redis down")


def _settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _limiter(backend: object) -> RateLimiter:
    return RateLimiter(backend, _settings())  # type: ignore[arg-type]


def _request(ip: str = "203.0.113.7") -> object:
    return types.SimpleNamespace(client=types.SimpleNamespace(host=ip))


@pytest.mark.unit
async def test_window_allows_up_to_limit_then_blocks() -> None:
    limiter = _limiter(FakeRateLimitBackend(_Clock()))
    rule = RateLimitRule(limit=3, window_seconds=60)
    for _ in range(3):
        assert await limiter.check_all([("s", "id", rule)]) is None
    blocked = await limiter.check_all([("s", "id", rule)])
    assert blocked is not None
    assert blocked.allowed is False
    assert blocked.retry_after > 0


@pytest.mark.unit
async def test_window_expiry_restores_service() -> None:
    clock = _Clock()
    limiter = _limiter(FakeRateLimitBackend(clock))
    rule = RateLimitRule(limit=2, window_seconds=60)
    assert await limiter.check_all([("s", "id", rule)]) is None
    assert await limiter.check_all([("s", "id", rule)]) is None
    assert await limiter.check_all([("s", "id", rule)]) is not None  # blocked
    clock.advance(61)
    assert await limiter.check_all([("s", "id", rule)]) is None  # window rolled over


@pytest.mark.unit
async def test_per_ip_and_per_account_keys_are_separate() -> None:
    backend = FakeRateLimitBackend(_Clock())
    limiter = _limiter(backend)
    ip_rule = RateLimitRule(limit=10, window_seconds=60)
    acct_rule = RateLimitRule(limit=1, window_seconds=60)
    # First request: both buckets under limit.
    assert await limiter.check_all([("ip", "1.2.3.4", ip_rule), ("acct", "bob", acct_rule)]) is None
    # Second request: account bucket (limit 1) trips though the IP bucket has room.
    result = await limiter.check_all([("ip", "1.2.3.4", ip_rule), ("acct", "bob", acct_rule)])
    assert result is not None and result.allowed is False
    # Two distinct keys exist.
    assert len(backend.store) == 2


@pytest.mark.unit
async def test_fail_open_on_backend_exception(caplog: pytest.LogCaptureFixture) -> None:
    limiter = _limiter(RaisingBackend())
    with caplog.at_level("WARNING"):
        result = await limiter.check_all([("s", "id", RateLimitRule(1, 60))])
    assert result is None  # allowed despite backend fault
    assert any("failing open" in r.message for r in caplog.records)


@pytest.mark.unit
async def test_non_positive_limit_disables_bucket() -> None:
    backend = FakeRateLimitBackend(_Clock())
    limiter = _limiter(backend)
    for _ in range(100):
        assert await limiter.check_all([("s", "id", RateLimitRule(0, 60))]) is None
    assert backend.store == {}  # bucket never touched the backend


@pytest.mark.unit
async def test_enforce_login_normalises_email_case() -> None:
    backend = FakeRateLimitBackend(_Clock())
    limiter = _limiter(backend)
    await limiter.enforce_login(_request(), "USER@Example.com")
    await limiter.enforce_login(_request(), "user@example.com")
    # The account bucket for both casings is the SAME key (lowercased).
    acct_key = f"rl:login:acct:{_hash_identifier('user@example.com')}"
    assert backend.store[acct_key][0] == 2


@pytest.mark.unit
async def test_keys_carry_no_raw_identifier() -> None:
    backend = FakeRateLimitBackend(_Clock())
    limiter = _limiter(backend)
    await limiter.enforce_login(_request(ip="198.51.100.9"), "secret.person@example.com")
    for key in backend.store:
        assert "secret.person@example.com" not in key
        assert "198.51.100.9" not in key


@pytest.mark.unit
async def test_enforce_raises_429_with_retry_after() -> None:
    from fastapi import HTTPException

    # Force the login account bucket to 1 by constructing tight settings.
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        rate_limit_login_account_per_window=1,
        rate_limit_login_ip_per_window=100,
    )
    limiter = RateLimiter(FakeRateLimitBackend(_Clock()), settings)
    await limiter.enforce_login(_request(), "victim@example.com")
    with pytest.raises(HTTPException) as exc:
        await limiter.enforce_login(_request(), "victim@example.com")
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


@pytest.mark.unit
def test_get_rate_limiter_falls_back_to_fail_open_when_unwired() -> None:
    # A request whose app.state has no rate_limiter yields a real limiter that
    # allows everything (byte-identical to pre-slice behaviour).
    fake_state = types.SimpleNamespace()
    fake_app = types.SimpleNamespace(state=fake_state)
    request = types.SimpleNamespace(app=fake_app)
    limiter = get_rate_limiter(request)  # type: ignore[arg-type]
    assert isinstance(limiter, RateLimiter)
