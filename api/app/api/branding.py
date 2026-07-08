"""Deployment-branding endpoints — BRAND-1a (fork, ADR-F068).

White-label surface over the singleton ``deployment_branding`` row
(migration 0090):

* ``GET  /api/v1/branding``       — **unauthenticated**; the product name,
  validated accent palette and logo cache-buster the web shell needs BEFORE
  login (the login page is a branded surface). Rate-limited per-IP
  (bootstrap-status precedent) and cacheable for 5 minutes.
* ``GET  /api/v1/branding/logo``  — **unauthenticated**; the stored raster
  logo bytes under the SNIFFED content type, immutable-cacheable (the URL
  carries ``?v=logo_version``). 404 when no logo is set.
* ``PUT  /api/v1/branding``       — admin-only; upserts name + palette.
  ``product_name`` rejects control characters (it lands in SMTP subject
  headers — header-injection surface); ``palette`` is validated against a
  CLOSED per-theme token allowlist (ADR-F068 — ``--primary`` is ink by
  design and deliberately NOT brandable).
* ``POST /api/v1/branding/logo``  — admin-only; raster-only upload. Magic
  bytes are sniffed (PNG/JPEG/WEBP) and the SNIFFED type is stored — the
  client-declared ``content_type`` header is never trusted, so SVG (script
  risk on an unauth surface) is impossible by construction. Hard 512 KB cap.
* ``DELETE /api/v1/branding/logo`` — admin-only; clears the logo.

The router is mounted WITHOUT the ``_active`` gate (next to the bootstrap
router in :mod:`app.api`), so every WRITE endpoint carries the ``AdminUser``
dependency as a parameter — the ``organization_profile`` PUT pattern.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.audit import audit_action
from app.db.session import get_db
from app.errors import NotFound, PayloadTooLarge, ValidationError

# The brand-validation rules (name cap, hex shape, control-char predicate,
# palette allowlist) live on the MODEL module — the single source shared with
# the first-boot env seeder (app/admin_bootstrap.py), so the two boundaries
# cannot drift (ADR-F068).
from app.models.deployment_branding import (
    ALLOWED_PALETTE_THEMES,
    ALLOWED_PALETTE_TOKENS,
    HEX_COLOR_RE,
    PRODUCT_NAME_MAX,
    DeploymentBranding,
    contains_control_chars,
)
from app.security.rate_limit import RateLimiter, get_rate_limiter

router = APIRouter(prefix="/branding", tags=["branding"])

# Raster-only logo constraints (ADR-F068): sniffed magic bytes → served
# content type. SVG fails the sniff by construction (no script surface); no
# server-side decode ⇒ no pillow dependency, no decompression-bomb surface.
LOGO_MAX_BYTES = 512 * 1024


def _sniff_logo_content_type(data: bytes) -> str | None:
    """Return the raster MIME type for ``data``'s magic bytes, or ``None``.

    PNG ``\\x89PNG\\r\\n\\x1a\\n`` / JPEG ``\\xff\\xd8\\xff`` / WEBP
    ``RIFF????WEBP``. The result — never the upload's client-declared
    header — is what gets stored and later served (with ``nosniff``).
    """

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class BrandingResponse(BaseModel):
    """GET response shape; the write endpoints also return it on success.

    ``logo_version`` is an OPAQUE cache-buster when a logo is set, else
    ``None`` — the web client appends it as ``?v=`` so the immutable-cached
    logo URL busts on change. It derives from the row's ``updated_at`` at
    MILLISECOND resolution (whole seconds would let two writes inside the
    same second share a version, pinning the year-long-cached old logo);
    clients must not parse it. Never bytes, never user data.
    """

    product_name: str
    palette: dict[str, dict[str, str]]
    logo_version: int | None = None
    updated_at: datetime | None = None


class BrandingUpdateRequest(BaseModel):
    """PUT body. Empty ``product_name`` / ``{}`` palette restore the default
    brand without deleting the row (upsert semantics, like the org profile).
    """

    product_name: str = Field(min_length=0, max_length=PRODUCT_NAME_MAX)
    palette: dict[str, dict[str, str]] = Field(default_factory=dict)

    @field_validator("product_name")
    @classmethod
    def _reject_control_chars(cls, v: str) -> str:
        # The name lands in SMTP SUBJECT headers (lifecycle_email) — CR/LF is
        # a header-injection vector, and no control/format/line-separator
        # character (C0, C1, DEL, U+2028/29, RTL overrides) belongs in a
        # product name. Reject, don't sanitize (CLAUDE.md boundary rule).
        if contains_control_chars(v):
            raise ValueError("product_name must not contain control characters (including CR/LF)")
        return v

    @field_validator("palette")
    @classmethod
    def _validate_palette(cls, v: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        # CLOSED allowlist (ADR-F068): name the offender so the admin UI can
        # surface a precise error, but never echo more than the key itself.
        for theme, tokens in v.items():
            if theme not in ALLOWED_PALETTE_THEMES:
                allowed = ", ".join(sorted(ALLOWED_PALETTE_THEMES))
                raise ValueError(f"unknown palette theme '{theme}' (allowed: {allowed})")
            for token, value in tokens.items():
                if token not in ALLOWED_PALETTE_TOKENS:
                    allowed = ", ".join(sorted(ALLOWED_PALETTE_TOKENS))
                    raise ValueError(
                        f"unknown palette token '{token}' in theme '{theme}' (allowed: {allowed})"
                    )
                if not HEX_COLOR_RE.fullmatch(value):
                    raise ValueError(
                        f"palette value for '{theme}.{token}' must be a 6-digit hex "
                        "colour like #0070f3"
                    )
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_singleton(db: AsyncSession) -> DeploymentBranding | None:
    """Return the single ``deployment_branding`` row, or ``None`` if unset.

    The DB enforces "at most one row" via the partial unique index on
    ``((true))`` (migration 0090); this helper centralises the read.
    """

    stmt = select(DeploymentBranding).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _to_response(row: DeploymentBranding | None) -> BrandingResponse:
    """Wire shape for a (possibly absent) singleton — empty row ⇒ defaults."""

    if row is None:
        return BrandingResponse(product_name="", palette={}, logo_version=None, updated_at=None)
    return BrandingResponse(
        product_name=row.product_name,
        palette=row.palette or {},
        # Millisecond resolution: whole seconds would let two logo writes in
        # the same second share a version, leaving the immutable-cached (1y)
        # old logo unbustable for clients that fetched in between.
        logo_version=(
            int(row.updated_at.timestamp() * 1000) if row.logo_bytes is not None else None
        ),
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=BrandingResponse,
    summary="Get the deployment's branding (unauthenticated)",
)
async def get_branding(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> BrandingResponse:
    """GET /api/v1/branding — unauthenticated by design.

    The login / accept-invite / reset-password pages are branded surfaces
    consulted BEFORE the user has credentials, so this read carries no auth.
    The response is exactly the public fields — no user data, no version
    fingerprints — and an empty singleton returns 200 with defaults, never
    404. ``max-age=300`` bounds staleness (the SPA refetches each boot).
    """

    # ADR-F068 — per-IP cap on the unauth surface (bootstrap-status precedent).
    await limiter.enforce_branding(request)
    row = await _load_singleton(db)
    response.headers["Cache-Control"] = "public, max-age=300"
    return _to_response(row)


@router.get(
    "/logo",
    response_class=Response,
    summary="Get the deployment's logo bytes (unauthenticated)",
    responses={
        200: {"content": {"image/png": {}, "image/jpeg": {}, "image/webp": {}}},
        404: {"description": "No logo is set"},
    },
)
async def get_branding_logo(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> Response:
    """GET /api/v1/branding/logo — the stored raster bytes.

    Served under the SNIFFED content type stored at upload time (never the
    client-declared header) with ``nosniff`` + ``inline`` so the browser
    can't be talked into treating it as anything but an image. The URL is
    version-busted (``?v=logo_version``), so ``immutable`` is safe.
    """

    await limiter.enforce_branding(request)
    row = await _load_singleton(db)
    if row is None or row.logo_bytes is None or row.logo_content_type is None:
        raise NotFound(message="No logo is set.")
    return Response(
        content=row.logo_bytes,
        media_type=row.logo_content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


@router.put(
    "",
    response_model=BrandingResponse,
    summary="Update the deployment's branding (admin only)",
    responses={
        200: {"model": BrandingResponse},
        401: {"description": "Bearer token missing or invalid"},
        403: {"description": "Caller is not an admin"},
        422: {"description": "Invalid product_name or palette"},
    },
)
async def put_branding(
    payload: BrandingUpdateRequest,
    request: Request,
    user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandingResponse:
    """PUT /api/v1/branding — admin upsert of name + palette.

    Idempotent: update the singleton in place if it exists (the trigger
    maintains ``updated_at``), insert otherwise. The logo columns are NOT
    touched here — they have their own POST/DELETE below.

    Audit-logged as ``deployment_branding.updated`` with counts/lengths
    only (never the values themselves).
    """

    row = await _load_singleton(db)
    if row is None:
        row = DeploymentBranding(
            product_name=payload.product_name,
            palette=payload.palette,
            updated_by=user.id,
        )
        db.add(row)
    else:
        row.product_name = payload.product_name
        row.palette = payload.palette
        row.updated_by = user.id

    await audit_action(
        db,
        user_id=user.id,
        action="deployment_branding.updated",
        resource_type="deployment_branding",
        resource_id=None,
        request=request,
        details={
            "product_name_length": len(payload.product_name),
            "palette_theme_count": len(payload.palette),
            "palette_token_count": sum(len(tokens) for tokens in payload.palette.values()),
        },
    )
    await db.commit()
    await db.refresh(row)
    return _to_response(row)


@router.post(
    "/logo",
    response_model=BrandingResponse,
    summary="Upload the deployment's logo (admin only; raster only)",
    responses={
        200: {"model": BrandingResponse},
        401: {"description": "Bearer token missing or invalid"},
        403: {"description": "Caller is not an admin"},
        413: {"description": "Logo exceeds the 512 KB cap"},
        422: {"description": "Not a PNG/JPEG/WEBP raster image"},
    },
)
async def post_branding_logo(
    request: Request,
    user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(description="PNG, JPEG or WEBP logo, ≤512 KB.")],
) -> BrandingResponse:
    """POST /api/v1/branding/logo — admin raster upload.

    Reads at most ``LOGO_MAX_BYTES + 1`` bytes (hard cap — 413 beyond it)
    and sniffs the magic bytes; the SNIFFED type is stored and later served.
    ``file.content_type`` is deliberately ignored — the client header is
    attacker-controlled (:mod:`app.api.files` trusts it for user documents;
    this unauth-served surface must not). SVG fails the sniff by
    construction. No decode ⇒ no pillow, no decompression-bomb surface.
    """

    data = await file.read(LOGO_MAX_BYTES + 1)
    if len(data) > LOGO_MAX_BYTES:
        raise PayloadTooLarge(
            message=f"Logo exceeds the {LOGO_MAX_BYTES // 1024} KB limit.",
            details={"limit_bytes": LOGO_MAX_BYTES},
        )
    sniffed = _sniff_logo_content_type(data)
    if sniffed is None:
        raise ValidationError(
            message="Logo must be a PNG, JPEG or WEBP raster image (magic-byte check failed).",
            http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    row = await _load_singleton(db)
    if row is None:
        row = DeploymentBranding(
            logo_bytes=data,
            logo_content_type=sniffed,
            updated_by=user.id,
        )
        db.add(row)
    else:
        row.logo_bytes = data
        row.logo_content_type = sniffed
        row.updated_by = user.id

    await audit_action(
        db,
        user_id=user.id,
        action="deployment_branding.logo_uploaded",
        resource_type="deployment_branding",
        resource_id=None,
        request=request,
        details={"logo_size_bytes": len(data), "logo_content_type": sniffed},
    )
    await db.commit()
    await db.refresh(row)
    return _to_response(row)


@router.delete(
    "/logo",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the deployment's logo (admin only)",
    responses={
        204: {"description": "Logo cleared"},
        401: {"description": "Bearer token missing or invalid"},
        403: {"description": "Caller is not an admin"},
        404: {"description": "No logo is set"},
    },
)
async def delete_branding_logo(
    request: Request,
    user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """DELETE /api/v1/branding/logo — clear the stored logo.

    404 when no logo is set (mirrors the GET), 204 on success. The UPDATE
    bumps ``updated_at`` via the trigger, so cached logo URLs bust.
    """

    row = await _load_singleton(db)
    if row is None or row.logo_bytes is None:
        raise NotFound(message="No logo is set.")
    row.logo_bytes = None
    row.logo_content_type = None
    row.updated_by = user.id

    await audit_action(
        db,
        user_id=user.id,
        action="deployment_branding.logo_deleted",
        resource_type="deployment_branding",
        resource_id=None,
        request=request,
        details={},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
