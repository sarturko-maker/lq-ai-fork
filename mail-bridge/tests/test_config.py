"""Settings fail-fast — INTAKE-2.

The bridge env vars use the ``${VAR:-}`` (empty-default) form in
docker-compose.yml so a default ``docker compose up`` with the ``mail`` profile
inactive does not abort at interpolation time. The "required when the profile is
active" guarantee therefore lives in ``Settings``: an empty required credential
must fail fast at startup, not produce a bridge that quietly forwards nothing.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

_VALID = {
    "agentmail_api_key": "key",
    "agentmail_inbox_address": "intake@bridge.test",
    "lq_ai_backend_url": "http://api:8000",
    "lq_ai_bridge_token": "token",
}


def test_valid_settings_construct() -> None:
    settings = Settings(**_VALID)
    assert settings.agentmail_inbox_address == "intake@bridge.test"
    assert settings.otel_service_name == "lq-ai-mail-bridge"
    assert settings.log_level == "INFO"


@pytest.mark.parametrize("field", sorted(_VALID))
def test_empty_required_field_rejected(field: str) -> None:
    bad = {**_VALID, field: ""}
    with pytest.raises(ValidationError) as exc:
        Settings(**bad)
    assert "required when the mail profile is enabled" in str(exc.value)


def test_whitespace_only_required_field_rejected() -> None:
    bad = {**_VALID, "agentmail_api_key": "   "}
    with pytest.raises(ValidationError) as exc:
        Settings(**bad)
    assert "agentmail_api_key is required when the mail profile is enabled" in str(exc.value)


def test_webhook_secret_is_optional() -> None:
    """No Svix secret ⇒ dev deployment ⇒ websocket-only ingress."""

    assert Settings(**_VALID).agentmail_webhook_secret is None


def test_blank_webhook_secret_normalises_to_none() -> None:
    """Compose's ``${AGENTMAIL_WEBHOOK_SECRET:-}`` hands us "" when unset."""

    settings = Settings(**_VALID, agentmail_webhook_secret="   ")
    assert settings.agentmail_webhook_secret is None


def test_webhook_secret_survives_when_set() -> None:
    settings = Settings(**_VALID, agentmail_webhook_secret="whsec_abc")
    assert settings.agentmail_webhook_secret == "whsec_abc"


def test_log_level_reads_the_namespaced_compose_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compose passes LQ_AI_MAIL_BRIDGE_LOG_LEVEL; the alias must pick it up."""

    monkeypatch.setenv("LQ_AI_MAIL_BRIDGE_LOG_LEVEL", "DEBUG")
    assert Settings(**_VALID).log_level == "DEBUG"


@pytest.mark.parametrize("garbage", ["LOUD", "", "  ", "42"])
def test_unknown_log_level_falls_back_to_info(
    monkeypatch: pytest.MonkeyPatch, garbage: str
) -> None:
    """A typo in an OPTIONAL var must not stop the bridge booting.

    ``logging.basicConfig(level=…)`` raises on an unknown name, which would turn
    one bad env var into an intake mailbox that silently stops being read.
    """

    monkeypatch.setenv("LQ_AI_MAIL_BRIDGE_LOG_LEVEL", garbage)
    assert Settings(**_VALID).log_level == "INFO"


def test_known_log_level_is_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LQ_AI_MAIL_BRIDGE_LOG_LEVEL", "debug")
    assert Settings(**_VALID).log_level == "DEBUG"
