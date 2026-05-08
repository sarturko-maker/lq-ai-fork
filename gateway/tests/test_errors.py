"""Unit tests for the gateway/ side of the lq_ai.errors hierarchy.

Per ADR 0003, the gateway exception hierarchy renders to the canonical
``{"error": {"code": ..., "message": ..., "details": ...}}`` envelope
documented as ``GatewayError`` in ``docs/api/gateway-openapi.yaml``.
These tests pin the envelope shape, the HTTP-status mapping, and the
handler registration so the wire shape is verified.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from app.errors import (
    CODE_ANONYMIZATION_FAILED,
    CODE_INVALID_MODEL,
    CODE_INVALID_REQUEST,
    CODE_NOT_IMPLEMENTED,
    CODE_PROVIDER_UNAVAILABLE,
    CODE_RATE_LIMIT_EXCEEDED,
    CODE_TIER_BELOW_MINIMUM,
    CODE_TIER_DISALLOWED_GLOBALLY,
    CODE_UNAUTHORIZED,
    AnonymizationFailed,
    InvalidModel,
    InvalidRequest,
    LQAIError,
    NotImplemented_,
    ProviderUnavailable,
    RateLimitExceeded,
    TierBelowMinimum,
    TierDisallowedGlobally,
    Unauthorized,
)
from app.main import _lqai_error_handler, app

# --- Construction & envelope shape -------------------------------------------


@pytest.mark.unit
def test_envelope_uses_error_wrapper_with_inner_code_message_details() -> None:
    err = ProviderUnavailable(
        "anthropic 503",
        details={"upstream_status": 503, "provider": "anthropic-prod"},
    )
    envelope = err.to_envelope()
    assert "error" in envelope
    inner = envelope["error"]
    assert inner["code"] == CODE_PROVIDER_UNAVAILABLE
    assert inner["message"] == "anthropic 503"
    assert inner["details"] == {"upstream_status": 503, "provider": "anthropic-prod"}


@pytest.mark.unit
def test_envelope_carries_empty_details_when_none_supplied() -> None:
    err = InvalidModel("not a known model")
    assert err.to_envelope() == {
        "error": {
            "code": CODE_INVALID_MODEL,
            "message": "not a known model",
            "details": {},
        }
    }


@pytest.mark.unit
def test_per_instance_overrides_take_precedence() -> None:
    err = LQAIError("oops", code="invalid_request", http_status=418)
    assert err.effective_code == "invalid_request"
    assert err.effective_http_status == 418


# --- HTTP-status mapping per subclass ----------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("cls", "expected_status", "expected_code"),
    [
        (TierBelowMinimum, status.HTTP_403_FORBIDDEN, CODE_TIER_BELOW_MINIMUM),
        (TierDisallowedGlobally, status.HTTP_403_FORBIDDEN, CODE_TIER_DISALLOWED_GLOBALLY),
        (AnonymizationFailed, status.HTTP_502_BAD_GATEWAY, CODE_ANONYMIZATION_FAILED),
        (InvalidModel, status.HTTP_400_BAD_REQUEST, CODE_INVALID_MODEL),
        (ProviderUnavailable, status.HTTP_502_BAD_GATEWAY, CODE_PROVIDER_UNAVAILABLE),
        (RateLimitExceeded, status.HTTP_429_TOO_MANY_REQUESTS, CODE_RATE_LIMIT_EXCEEDED),
        (InvalidRequest, status.HTTP_400_BAD_REQUEST, CODE_INVALID_REQUEST),
        (NotImplemented_, status.HTTP_501_NOT_IMPLEMENTED, CODE_NOT_IMPLEMENTED),
        (Unauthorized, status.HTTP_502_BAD_GATEWAY, CODE_UNAUTHORIZED),
    ],
)
def test_each_subclass_has_documented_code_and_status(
    cls: type[LQAIError], expected_status: int, expected_code: str
) -> None:
    err = cls("test")
    assert err.effective_http_status == expected_status
    assert err.effective_code == expected_code


# --- FastAPI exception handler round-trip ------------------------------------


@pytest.mark.unit
async def test_handler_renders_canonical_envelope() -> None:
    """The handler in app.main converts LQAIError instances correctly."""

    test_app = FastAPI()
    test_app.add_exception_handler(LQAIError, _lqai_error_handler)

    @test_app.get("/raise")
    async def _raise() -> None:
        raise InvalidModel("model 'foo' is not configured", details={"model": "foo"})

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/raise")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body == {
        "error": {
            "code": CODE_INVALID_MODEL,
            "message": "model 'foo' is not configured",
            "details": {"model": "foo"},
        }
    }


@pytest.mark.unit
async def test_app_main_handler_is_registered() -> None:
    """The real gateway app has the LQAIError handler wired."""

    assert LQAIError in app.exception_handlers
