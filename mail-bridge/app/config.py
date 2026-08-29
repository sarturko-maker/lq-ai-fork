"""Runtime configuration for the LQ.AI Mail Bridge — INTAKE-2 (ADR-F086).

Loaded from environment variables via ``pydantic-settings`` (same pattern as
``slack-bridge/``, ``teams-bridge/``, ``api/`` and ``gateway/``).

ADR-F086: **the mail-bridge is the sole holder of mailbox credentials** — the
gateway key-holder pattern applied to email. ``AGENTMAIL_API_KEY`` (and, in
production, ``AGENTMAIL_WEBHOOK_SECRET``) exist in THIS service's environment
and nowhere else: not in ``api/``, not in ``web/``, never in a log line, an
error body, or a test fixture.

The fields divide into three groups:

* **Provider credentials** — ``AGENTMAIL_API_KEY`` + ``AGENTMAIL_INBOX_ADDRESS``
  (AgentMail's ``inbox_id`` IS the email address). Both required.
  ``AGENTMAIL_WEBHOOK_SECRET`` is the Svix signing secret and is OPTIONAL: it is
  set only in a deployment that has a public URL AgentMail can POST to. Its
  presence is what mounts the webhook route (see ``app.main``); the dev box has
  no public endpoint and runs the websocket subscriber instead.
* **LQ.AI-side coordinates** — ``LQ_AI_BACKEND_URL`` (where the api is reachable
  from inside the compose network) and ``LQ_AI_BRIDGE_TOKEN`` (the shared secret
  for the internal bridge ↔ api channel, in BOTH directions: the bridge presents
  it on ``POST /internal/intake/emails``, and INTAKE-4's api → bridge ``/send``
  call presents it back).
* **Observability** — the OTel pair, opt-in per PRD §5.7, plus the log level.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Bridge runtime configuration."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    agentmail_api_key: str = Field(
        ...,
        description=(
            "AgentMail API key. The ONLY copy in the deployment (ADR-F086: "
            "bridge-held mail credentials). Never logged, never serialized, "
            "never forwarded to the api."
        ),
    )
    agentmail_inbox_address: str = Field(
        ...,
        description=(
            "The intake mailbox address. AgentMail's inbox_id IS the address "
            "(verified live — docs/fork/evidence/intake-probe/findings.md), so "
            "this doubles as the envelope's inbox_id, which the api resolves "
            "against its intake_mailboxes binding."
        ),
    )
    agentmail_webhook_secret: str | None = Field(
        default=None,
        description=(
            "Svix signing secret (whsec_…) for the production webhook ingress. "
            "OPTIONAL: when unset the webhook route is not mounted at all and "
            "the bridge relies solely on the websocket subscriber (dev)."
        ),
    )

    lq_ai_backend_url: str = Field(
        ...,
        description=(
            "Base URL of the LQ.AI api as reachable from inside the bridge's "
            "network (e.g. http://api:8000 in compose)."
        ),
    )
    lq_ai_bridge_token: str = Field(
        ...,
        description=(
            "Shared secret on the internal bridge ↔ api channel. The bridge "
            "sends it as a Bearer on POST /internal/intake/emails; it also "
            "gates this service's own POST /send (INTAKE-4's outbound path)."
        ),
    )

    # Observability — opt-in per PRD §5.7.
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None,
        description=(
            "OpenTelemetry collector endpoint. If unset, the bridge does not "
            "initialise the TracerProvider — no telemetry leaves the deployment "
            "(PRD §5.7 no-telemetry-by-default)."
        ),
    )
    otel_service_name: str = Field(
        default="lq-ai-mail-bridge",
        description="Resource attribute reported on every span.",
    )

    log_level: str = Field(
        default="INFO",
        # The compose block passes LQ_AI_MAIL_BRIDGE_LOG_LEVEL (namespaced, so
        # one .env can hold a different level per bridge). AliasChoices keeps
        # the bare LOG_LEVEL working too.
        validation_alias=AliasChoices("LQ_AI_MAIL_BRIDGE_LOG_LEVEL", "LOG_LEVEL"),
        description="Python logging level for the bridge process.",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def _known_log_level(cls, value: object) -> object:
        """Fall back to INFO on anything ``logging`` would not recognise.

        ``logging.basicConfig(level=…)`` raises on an unknown name, which would
        turn a typo in one optional env var into a bridge that refuses to boot
        and therefore an intake mailbox that silently stops being read.
        """

        if not isinstance(value, str):
            return "INFO"
        candidate = value.strip().upper()
        if candidate not in {"CRITICAL", "FATAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG"}:
            return "INFO"
        return candidate

    @field_validator("agentmail_webhook_secret", mode="before")
    @classmethod
    def _blank_webhook_secret_is_unset(cls, value: object) -> object:
        """An empty ``AGENTMAIL_WEBHOOK_SECRET`` means "no webhook ingress".

        Compose interpolates the var with the ``${VAR:-}`` empty-default form,
        so an operator who has not configured a Svix endpoint hands us ``""``
        rather than nothing at all. Normalising it to ``None`` here keeps the
        "webhook route mounted iff a secret exists" test in ``app.main`` a
        single ``is None`` check.
        """

        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "agentmail_api_key",
        "agentmail_inbox_address",
        "lq_ai_backend_url",
        "lq_ai_bridge_token",
    )
    @classmethod
    def _required_when_mail_enabled(cls, value: str, info: ValidationInfo) -> str:
        """Reject empty operator credentials at bridge startup.

        These vars use the ``${VAR:-}`` (empty-default) form in
        ``docker-compose.yml`` so a default ``docker compose up`` with the
        ``mail`` profile inactive does not abort at interpolation time (Compose
        interpolates every service before profile filtering — DE-305, the same
        trap the slack-bridge documents). The "required when the profile is
        active" guarantee moves here: the bridge only constructs ``Settings``
        when its container starts (i.e. when the ``mail`` profile is enabled),
        so an empty value fails fast with a clear message instead of starting a
        bridge that silently forwards nothing.
        """

        if not value or not value.strip():
            raise ValueError(f"{info.field_name} is required when the mail profile is enabled")
        return value


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a process-cached :class:`Settings` instance.

    Cached so the env-var read happens once at process start. Tests that need a
    different value construct ``Settings(...)`` directly and hand it to
    ``create_app(settings=…)`` — nothing here is reached for as a global.
    """

    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
