"""Auth-surface rate limiting — SAAS-2 (ADR-F059 §6-item-1).

Per-IP and per-account fixed-window counters on the authentication endpoints,
enforced on the EXISTING Redis client (``app.cache.get_redis``) — no new
dependency (CLAUDE.md SBOM posture). The counters are the classic atomic
``INCR`` + first-hit ``EXPIRE`` pattern run inside a single Lua script via
``register_script`` so a crash between the two commands can never leave a
TTL-less key that would lock a bucket forever.

Design (DI, CLAUDE.md):
  * ``RateLimiter`` takes a ``RateLimitBackend`` (a thin seam over the redis
    client) + ``Settings`` as constructor args. It is built ONCE in the api
    lifespan and stored on ``app.state``; routes reach it through the
    :func:`get_rate_limiter` FastAPI dependency. No module-level singleton.
  * Tests inject a hand-rolled in-memory ``RateLimitBackend`` through the same
    seam (no ``fakeredis`` dependency, no monkeypatching).

Posture:
  * On limit: HTTP 429 with a ``Retry-After`` header. The response shape is
    identical regardless of whether the account exists (no existence leak).
  * On Redis unavailability: FAIL OPEN with a WARNING log — a Redis outage must
    never lock legitimate users out of authentication (redis is in-stack). A
    Redis exception NEVER 500s an auth endpoint.
  * Keys carry NO secrets and NO raw identifiers: the per-account identifier is
    hashed (``sha256(identifier)[:16]``) so an email/user-id never lands in a
    Redis key or a log line.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.config import Settings

log = logging.getLogger(__name__)

# INCR the counter; set the window TTL only on the first hit (count == 1) so a
# steady stream can never keep pushing the expiry out. Return both the count and
# the remaining TTL so the caller can emit an accurate Retry-After. Atomic: the
# whole script runs as one Redis command.
_INCR_EXPIRE_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True)
class RateLimitRule:
    """A single bucket: at most ``limit`` events per ``window_seconds``."""

    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a single bucket check."""

    allowed: bool
    retry_after: int


class RateLimitBackend(Protocol):
    """The injectable seam. Implementations must never raise for a normal miss."""

    async def incr_with_expiry(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Increment ``key``, ensuring a TTL of ``window_seconds``.

        Returns ``(count_in_window, ttl_remaining_seconds)``.
        """
        ...


class RedisRateLimitBackend:
    """``RateLimitBackend`` over the shared async redis client."""

    def __init__(self, redis: object) -> None:
        # Typed as object to avoid importing redis types here; the client is the
        # process-global from app.cache.get_redis(). register_script binds the
        # script to this client and uses EVALSHA (with EVAL fallback on NOSCRIPT).
        self._script = redis.register_script(_INCR_EXPIRE_LUA)  # type: ignore[attr-defined]

    async def incr_with_expiry(self, key: str, window_seconds: int) -> tuple[int, int]:
        result = await self._script(keys=[key], args=[window_seconds])
        count, ttl = int(result[0]), int(result[1])
        return count, ttl


class _NullRateLimitBackend:
    """Fail-open backend used when no limiter was wired (e.g. lifespan skipped).

    Returns count 0 so every check passes — behaviour is byte-identical to the
    pre-rate-limit code path.
    """

    async def incr_with_expiry(self, key: str, window_seconds: int) -> tuple[int, int]:
        return 0, 0


def _client_ip(request: Request) -> str:
    """Real client IP.

    Correct post trusted-proxy config (uvicorn ``--proxy-headers`` +
    ``FORWARDED_ALLOW_IPS`` rewrites ``request.client``); we NEVER parse
    ``X-Forwarded-For`` ourselves (ADR-F059 D4).
    """
    return request.client.host if request.client else "unknown"


def _hash_identifier(identifier: str) -> str:
    """Short, non-reversible tag for a key — no raw email/user-id in Redis/logs."""
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:16]


class RateLimiter:
    """Fixed-window rate limiter with named per-endpoint enforcement helpers."""

    def __init__(self, backend: RateLimitBackend, settings: Settings) -> None:
        self._backend = backend
        self._settings = settings

    # -- core -----------------------------------------------------------------

    @staticmethod
    def _key(scope: str, identifier: str) -> str:
        return f"rl:{scope}:{_hash_identifier(identifier)}"

    async def _hit(self, scope: str, identifier: str, rule: RateLimitRule) -> RateLimitResult:
        if rule.limit <= 0:
            # Non-positive limit disables the bucket.
            return RateLimitResult(allowed=True, retry_after=0)
        key = self._key(scope, identifier)
        try:
            count, ttl = await self._backend.incr_with_expiry(key, rule.window_seconds)
        except RedisError as exc:
            # Expected fail-open path: a Redis outage must never lock legitimate
            # users out of auth (ADR-F059). Quiet WARNING — this is operational.
            log.warning("rate-limit backend unavailable (scope=%s); failing open: %s", scope, exc)
            return RateLimitResult(allowed=True, retry_after=0)
        except Exception:
            # A NON-Redis exception is a bug (e.g. a backend refactor typo), not
            # an outage. Still fail open — the brake must never 500 an auth
            # endpoint — but log LOUDLY so a silently-disabled security control
            # is caught, not swallowed like a routine Redis blip.
            log.exception("rate-limit check errored unexpectedly (scope=%s); failing open", scope)
            return RateLimitResult(allowed=True, retry_after=0)
        if count > rule.limit:
            retry_after = ttl if ttl > 0 else rule.window_seconds
            return RateLimitResult(allowed=False, retry_after=retry_after)
        return RateLimitResult(allowed=True, retry_after=0)

    async def check_all(
        self, checks: Sequence[tuple[str, str, RateLimitRule]]
    ) -> RateLimitResult | None:
        """Run every (scope, identifier, rule) check; return the worst failure or None.

        All buckets are incremented (fixed-window semantics — each is an attempt),
        so a request that trips one bucket still counts against the others.
        """
        worst: RateLimitResult | None = None
        for scope, identifier, rule in checks:
            result = await self._hit(scope, identifier, rule)
            if not result.allowed and (worst is None or result.retry_after > worst.retry_after):
                worst = result
        return worst

    async def _enforce(self, checks: Sequence[tuple[str, str, RateLimitRule]]) -> None:
        result = await self.check_all(checks)
        if result is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(max(1, result.retry_after))},
            )

    # -- per-endpoint helpers -------------------------------------------------

    def _window(self) -> int:
        return self._settings.rate_limit_window_seconds

    async def enforce_login(self, request: Request, email: str) -> None:
        s = self._settings
        window = self._window()
        await self._enforce(
            [
                (
                    "login:ip",
                    _client_ip(request),
                    RateLimitRule(s.rate_limit_login_ip_per_window, window),
                ),
                (
                    "login:acct",
                    email.strip().lower(),
                    RateLimitRule(s.rate_limit_login_account_per_window, window),
                ),
            ]
        )

    async def enforce_refresh(self, request: Request) -> None:
        s = self._settings
        await self._enforce(
            [
                (
                    "refresh:ip",
                    _client_ip(request),
                    RateLimitRule(s.rate_limit_refresh_ip_per_window, self._window()),
                ),
            ]
        )

    async def enforce_mfa_verify(self, request: Request, account_id: str | None) -> None:
        s = self._settings
        window = self._window()
        checks: list[tuple[str, str, RateLimitRule]] = [
            (
                "mfa_verify:ip",
                _client_ip(request),
                RateLimitRule(s.rate_limit_mfa_verify_ip_per_window, window),
            ),
        ]
        if account_id:
            checks.append(
                (
                    "mfa_verify:acct",
                    account_id,
                    RateLimitRule(s.rate_limit_mfa_verify_account_per_window, window),
                )
            )
        await self._enforce(checks)

    async def enforce_change_password(self, request: Request, account_id: str) -> None:
        s = self._settings
        await self._enforce(
            [
                (
                    "change_password:acct",
                    account_id,
                    RateLimitRule(s.rate_limit_change_password_account_per_window, self._window()),
                ),
            ]
        )

    async def enforce_mfa_manage(self, request: Request, account_id: str, *, action: str) -> None:
        s = self._settings
        await self._enforce(
            [
                (
                    f"mfa_{action}:acct",
                    account_id,
                    RateLimitRule(s.rate_limit_mfa_manage_account_per_window, self._window()),
                ),
            ]
        )

    async def enforce_bootstrap_status(self, request: Request) -> None:
        s = self._settings
        await self._enforce(
            [
                (
                    "bootstrap_status:ip",
                    _client_ip(request),
                    RateLimitRule(s.rate_limit_bootstrap_status_ip_per_window, self._window()),
                ),
            ]
        )

    async def enforce_branding(self, request: Request) -> None:
        """BRAND-1a (ADR-F068) — per-IP brake on the unauthenticated branding
        reads (``GET /branding`` + ``GET /branding/logo``, one shared bucket).

        The data is public-by-design (the login page renders it), so the brake
        exists to bound scrape/bandwidth abuse, not to hide anything.
        """
        s = self._settings
        await self._enforce(
            [
                (
                    "branding:ip",
                    _client_ip(request),
                    RateLimitRule(s.rate_limit_branding_ip_per_window, self._window()),
                ),
            ]
        )

    async def enforce_password_reset_request(self, request: Request, email: str) -> None:
        """SETUP-3a (ADR-F061 D7) — per-IP + per-submitted-email on reset-request.

        Both buckets are checked whether or not the account exists, so a 429
        leaks no existence signal (the endpoint's uniform 202 does the same).
        """
        s = self._settings
        window = self._window()
        await self._enforce(
            [
                (
                    "password_reset_request:ip",
                    _client_ip(request),
                    RateLimitRule(s.rate_limit_password_reset_request_ip_per_window, window),
                ),
                (
                    "password_reset_request:email",
                    email.strip().lower(),
                    RateLimitRule(s.rate_limit_password_reset_request_email_per_window, window),
                ),
            ]
        )

    async def enforce_token_redeem(self, request: Request) -> None:
        """SETUP-3a (ADR-F061 D7) — per-IP brake shared by accept-invite +
        password-reset redemption.

        Per-IP only: the token itself is the identifier and must never be
        hashed into a Redis key or a log line.
        """
        s = self._settings
        await self._enforce(
            [
                (
                    "token_redeem:ip",
                    _client_ip(request),
                    RateLimitRule(s.rate_limit_token_redeem_ip_per_window, self._window()),
                ),
            ]
        )


def get_rate_limiter(request: Request) -> RateLimiter:
    """FastAPI dependency: the process-wide limiter wired in the lifespan.

    Falls back to a fail-open (null-backed) limiter when the lifespan did not
    wire one — e.g. ASGITransport tests that don't run lifespan — so the auth
    endpoints keep byte-identical behaviour there.
    """
    limiter = getattr(request.app.state, "rate_limiter", None)
    if isinstance(limiter, RateLimiter):
        return limiter
    from app.config import get_settings

    return RateLimiter(_NullRateLimitBackend(), get_settings())
