"""Pydantic schema for ``gateway.yaml``.

Mirrors the structure documented in ``gateway.yaml.example`` and PRD §4.4.
A3 only loads and validates the config; tier-policy enforcement (D1), tier
derivation (B4), and provider routing (B4) consume it later.

Validation rules enforced here:

* ``Provider.tier`` is in ``{1, 2, 3, 4, 5}``.
* ``TierPolicy.allowed_tiers_global`` is a non-empty subset of
  ``{1, 2, 3, 4, 5}``.
* Every ``ModelAlias.primary.provider`` (and each fallback's ``provider``)
  references a configured provider name.

Anything not strictly required for A3 acceptance is permissive
(``extra="allow"``) so future tasks can keep adding fields without rev-locking
the YAML schema.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --- Primitive type aliases ---------------------------------------------------

InferenceTier = Annotated[int, Field(ge=1, le=5)]
"""An Inference Tier (1-5 per PRD §1.5.2)."""

LogLevel = Literal["debug", "info", "warn", "error"]


# --- Server / auth ------------------------------------------------------------


class ServerConfig(BaseModel):
    """Top-level ``server:`` block."""

    model_config = ConfigDict(extra="forbid")

    host: str = "0.0.0.0"
    port: int = Field(default=8001, ge=1, le=65535)
    log_level: LogLevel = "info"


class GatewayAuthConfig(BaseModel):
    """``gateway_auth:`` — how the backend authenticates to the gateway."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    api_key_env: str = "LQ_AI_GATEWAY_KEY"


# --- Providers ----------------------------------------------------------------


ProviderType = Literal[
    "anthropic",
    "openai",
    "vertex",
    "cohere",
    "azure_openai",
    "bedrock",
    "ollama",
    "vllm",
    "openai_compatible",
]


class ProviderConfig(BaseModel):
    """One entry under ``providers:``.

    Keeps unknown provider-specific fields (``project_id``, ``region``,
    ``aws_region``, ``api_version``, etc.) by allowing extra fields. The
    per-type adapter (B3+) is responsible for reading what it needs.
    """

    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    type: ProviderType
    base_url: str = Field(min_length=1)
    # Some local providers (e.g., Ollama) legitimately have an empty string
    # here. Accept ``None`` and ``""`` to mean "no key required".
    api_key_env: str | None = None
    tier: InferenceTier
    models: list[str] = Field(default_factory=list)
    enabled: bool = True


# --- Model aliases ------------------------------------------------------------


class ModelTarget(BaseModel):
    """A specific (provider, model) target referenced from an alias."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class ModelAliasConfig(BaseModel):
    """One entry under ``model_aliases:``.

    Per PRD §4.4 / ``gateway.yaml.example``, an alias has a ``primary`` target
    and an optional ``fallback`` chain. Skills and the backend reference
    aliases (``smart``, ``fast``, ``budget``, ``local``, ``embedding``) rather
    than concrete provider/model pairs.
    """

    model_config = ConfigDict(extra="forbid")

    primary: ModelTarget
    fallback: list[ModelTarget] = Field(default_factory=list)


# --- Tier policy --------------------------------------------------------------


class TierPolicyConfig(BaseModel):
    """``tier_policy:`` — operator-level tier policy.

    A3 loads this; D1 enforces ``default_minimum_tier`` /
    ``privileged_minimum_tier`` refusals.
    """

    model_config = ConfigDict(extra="allow")

    allowed_tiers_global: list[InferenceTier] = Field(default_factory=lambda: [1, 2, 3, 4])
    default_minimum_tier: InferenceTier = 4
    privileged_minimum_tier: InferenceTier = 3
    warn_on_tiers: list[InferenceTier] = Field(default_factory=lambda: [4, 5])

    @field_validator("allowed_tiers_global")
    @classmethod
    def _allowed_tiers_must_be_non_empty(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("tier_policy.allowed_tiers_global must be non-empty")
        # Pydantic's ``InferenceTier`` already constrains each element to 1..5.
        # Deduplicate while preserving order for stable downstream behavior.
        seen: set[int] = set()
        deduped: list[int] = []
        for tier in value:
            if tier not in seen:
                seen.add(tier)
                deduped.append(tier)
        return deduped


# --- Rate limits / cost / validation / etc. (loose schemas) ------------------
#
# A3 doesn't enforce these; B6 / cost-tracker tasks tighten them as needed.
# We keep them as ``BaseModel`` with ``extra="allow"`` so the YAML round-trips
# cleanly and so future tasks can read what they need.


class RateLimitsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")


class AnonymizationConfig(BaseModel):
    """``anonymization:`` block. M2 feature; A3 just loads it."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = False


class CostTrackingConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True


class TelemetryConfig(BaseModel):
    model_config = ConfigDict(extra="allow")


class CircuitBreakerConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True


class RequestValidationConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_max_tokens: int = Field(default=16384, ge=1)
    max_messages_per_request: int = Field(default=100, ge=1)
    max_total_request_chars: int = Field(default=1_000_000, ge=1)
    large_context_threshold_tokens: int = Field(default=50_000, ge=1)


class DevModeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False


# --- Top-level config ---------------------------------------------------------


class GatewayConfig(BaseModel):
    """Full ``gateway.yaml`` shape.

    Loaded once on startup by :func:`app.config_loader.load_config` and
    attached to ``app.state.config``. Treat as immutable after startup.
    """

    model_config = ConfigDict(extra="allow")

    server: ServerConfig = Field(default_factory=ServerConfig)
    gateway_auth: GatewayAuthConfig = Field(default_factory=GatewayAuthConfig)
    providers: list[ProviderConfig] = Field(default_factory=list)
    model_aliases: dict[str, ModelAliasConfig] = Field(default_factory=dict)
    tier_policy: TierPolicyConfig = Field(default_factory=TierPolicyConfig)
    rate_limits: RateLimitsConfig = Field(default_factory=RateLimitsConfig)
    anonymization: AnonymizationConfig = Field(default_factory=AnonymizationConfig)
    cost_tracking: CostTrackingConfig = Field(default_factory=CostTrackingConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    request_validation: RequestValidationConfig = Field(default_factory=RequestValidationConfig)
    dev_mode: DevModeConfig = Field(default_factory=DevModeConfig)

    @model_validator(mode="after")
    def _aliases_reference_known_providers(self) -> GatewayConfig:
        """Every alias target must point at a configured provider.

        A typo here is the most common kind of misconfiguration ("provider:
        anthropic" when the configured name is "anthropic-prod"); refusing
        to start with a clear message beats failing on first request.
        """

        provider_names = {provider.name for provider in self.providers}
        if not provider_names:
            # Empty providers is allowed for tests / minimal configs, but then
            # there must also be no aliases referencing them.
            if self.model_aliases:
                raise ValueError(
                    "model_aliases configured but providers list is empty; "
                    "every alias must reference a provider"
                )
            return self

        for alias_name, alias in self.model_aliases.items():
            targets: list[tuple[str, ModelTarget]] = [("primary", alias.primary)]
            targets.extend(("fallback", target) for target in alias.fallback)
            for label, target in targets:
                if target.provider not in provider_names:
                    raise ValueError(
                        f"model_aliases.{alias_name}.{label} references unknown "
                        f"provider {target.provider!r}; configured providers: "
                        f"{sorted(provider_names)}"
                    )
        return self

    # --- Convenience accessors used by routers --------------------------------

    def alias_ids(self) -> list[str]:
        """Return the configured alias names in declaration order.

        Backs ``GET /v1/models``.
        """

        return list(self.model_aliases.keys())

    def to_models_payload(self) -> dict[str, Any]:
        """OpenAI ``GET /v1/models``-shaped response built from aliases.

        OpenAI's ``/v1/models`` returns ``{"object": "list", "data": [...]}``
        with each entry shaped as ``{"id", "object": "model", "created",
        "owned_by"}``. We use a fixed ``created=0`` because the gateway has
        no provider-relative creation timestamp; the field is included for
        client compatibility, not as a real value.
        """

        return {
            "object": "list",
            "data": [
                {
                    "id": alias_id,
                    "object": "model",
                    "created": 0,
                    "owned_by": "lq-ai-gateway",
                }
                for alias_id in self.alias_ids()
            ],
        }
