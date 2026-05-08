"""Gateway HTTP clients for inbound service-to-service calls.

The gateway is the security boundary; outbound provider calls live under
``app/providers/``. This namespace holds *backward* HTTP clients — calls
the gateway makes to the LQ.AI backend (``api/``) for content the
backend owns canonically, e.g. skill content per ADR 0006.

Modules:

* :mod:`app.clients.backend` — HTTP client + in-memory TTL cache for the
  backend's ``GET /api/v1/internal/skills/{name}`` endpoint, used by the
  C2 skill prompt assembler.
"""

from app.clients.backend import (
    BackendClient,
    BackendUnreachable,
    SkillCache,
    SkillFetchFailed,
    SkillNotFound,
)

__all__ = [
    "BackendClient",
    "BackendUnreachable",
    "SkillCache",
    "SkillFetchFailed",
    "SkillNotFound",
]
