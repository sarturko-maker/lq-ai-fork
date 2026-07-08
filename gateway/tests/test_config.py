"""Tests for ``app.config`` and ``app.config_loader``.

Covers the load-and-validate happy path, the ``${VAR}`` expansion contract,
and the error envelope when the file is missing / malformed.

We exercise the actual ``gateway.yaml.example`` from the repo root as the
canonical "valid config" because A3's verification is "the example config
loads cleanly". If a future PRD update changes the schema, this test will
be the first to catch it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import GatewayConfig, ModelTarget
from app.config_loader import ConfigLoadError, expand_env_vars, load_config

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = REPO_ROOT / "gateway.yaml.example"


# --- expand_env_vars ----------------------------------------------------------


@pytest.mark.unit
def test_expand_env_vars_uses_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LQ_AI_TEST_VAR", raising=False)
    assert expand_env_vars("${LQ_AI_TEST_VAR:-fallback}") == "fallback"


@pytest.mark.unit
def test_expand_env_vars_uses_env_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LQ_AI_TEST_VAR", "from-env")
    assert expand_env_vars("${LQ_AI_TEST_VAR:-fallback}") == "from-env"


@pytest.mark.unit
def test_expand_env_vars_yaml_typed_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """``${VAR:-true}`` must produce a real bool, not the string 'true'."""

    monkeypatch.delenv("LQ_AI_TEST_BOOL", raising=False)
    assert expand_env_vars("${LQ_AI_TEST_BOOL:-true}") is True
    monkeypatch.delenv("LQ_AI_TEST_INT", raising=False)
    assert expand_env_vars("${LQ_AI_TEST_INT:-8001}") == 8001


@pytest.mark.unit
def test_expand_env_vars_partial_substitution(monkeypatch: pytest.MonkeyPatch) -> None:
    """A placeholder embedded in a larger string stays a string."""

    monkeypatch.setenv("LQ_AI_TEST_REGION", "us-east-1")
    expanded = expand_env_vars("https://bedrock-runtime.${LQ_AI_TEST_REGION}.amazonaws.com")
    assert expanded == "https://bedrock-runtime.us-east-1.amazonaws.com"


@pytest.mark.unit
def test_expand_env_vars_required_var_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LQ_AI_REQUIRED", raising=False)
    with pytest.raises(ConfigLoadError, match="LQ_AI_REQUIRED"):
        expand_env_vars("${LQ_AI_REQUIRED}")


@pytest.mark.unit
def test_expand_env_vars_walks_nested_structures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LQ_AI_NESTED", "value")
    raw = {
        "outer": [
            {"inner": "${LQ_AI_NESTED}"},
            "${LQ_AI_NESTED}",
            42,  # non-string scalars pass through
        ]
    }
    assert expand_env_vars(raw) == {"outer": [{"inner": "value"}, "value", 42]}


# --- load_config: happy path on the real example -----------------------------


@pytest.fixture
def example_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the env vars referenced by ``gateway.yaml.example``.

    The example references several optional ``${VAR:-default}`` placeholders
    (no env action needed) and one or two required ``${VAR}`` placeholders
    that we satisfy here so the parse succeeds in tests.
    """

    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AZURE_OPENAI_RESOURCE", "test-openai")
    monkeypatch.setenv("LQ_AI_VERSION", "0.1.0-test")


@pytest.mark.unit
def test_load_config_parses_example(example_env: None) -> None:
    config = load_config(EXAMPLE_CONFIG)

    assert isinstance(config, GatewayConfig)

    # Providers from the example
    provider_names = {p.name for p in config.providers}
    assert {"anthropic-prod", "openai-prod", "ollama-local"} <= provider_names

    # Aliases from the example
    assert set(config.model_aliases.keys()) >= {"smart", "fast", "budget", "local"}

    # Tier policy
    assert config.tier_policy.allowed_tiers_global == [1, 2, 3, 4]
    assert config.tier_policy.default_minimum_tier == 4

    # M2-B3: Anonymization block typed shape.
    # The example ships anonymization.enabled=false (M2 feature flag)
    # and anonymization.apply_at_tiers=[3, 4, 5]. The middleware reads
    # both, so they need to be typed (not just ``extra="allow"``
    # passthroughs) so a typo in the YAML key surfaces as a config
    # error rather than a silent middleware no-op.
    assert config.anonymization.enabled is False
    assert config.anonymization.apply_at_tiers == [3, 4, 5]
    # Type discipline: an explicit ``list[int]`` so a string-list
    # would raise rather than silently passthrough.
    assert all(isinstance(t, int) for t in config.anonymization.apply_at_tiers)

    # M2-C1: Citation Engine block. ``judge_model`` defaults to ``fast``
    # so Stage 3's paraphrase judge runs on a smaller model than the
    # citation-generating model. The api/ pulls this value over the
    # ``/v1/citation-engine/config`` endpoint at startup.
    assert config.citation_engine.judge_model == "fast"


@pytest.mark.unit
def test_load_config_azure_foundry_entries_default_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AZ-CONFIG: the example's three Azure entries load with NO AZURE_* env.

    The example seeds fresh deployments (named-volume first boot), so it must
    parse with every ``${AZURE_*:-disabled}`` placeholder falling back to its
    default. Asserts the type mapping (azure-claude rides the ``anthropic``
    adapter; azure-mistral rides ``azure_openai`` on the services.ai host),
    the env-var plumbing, and the explicit tier-3 enterprise posture (the
    tier trap: ``openai_compatible`` would default to tier 1).
    """

    for var in (
        "AZURE_OPENAI_RESOURCE",
        "AZURE_OPENAI_API_KEY",
        "AZURE_ANTHROPIC_RESOURCE",
        "AZURE_ANTHROPIC_API_KEY",
        "AZURE_FOUNDRY_RESOURCE",
        "AZURE_FOUNDRY_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    config = load_config(EXAMPLE_CONFIG)
    providers = {provider.name: provider for provider in config.providers}

    azure_openai = providers["azure-openai"]
    assert azure_openai.type == "azure_openai"
    assert azure_openai.api_key_env == "AZURE_OPENAI_API_KEY"
    assert azure_openai.tier == 3
    assert azure_openai.base_url == "https://disabled.openai.azure.com"

    azure_claude = providers["azure-claude"]
    assert azure_claude.type == "anthropic"
    assert azure_claude.api_key_env == "AZURE_ANTHROPIC_API_KEY"
    assert azure_claude.tier == 3
    assert azure_claude.base_url == "https://disabled.services.ai.azure.com/anthropic"
    assert azure_claude.models == ["claude-sonnet-5", "claude-opus-4-8"]

    azure_mistral = providers["azure-mistral"]
    assert azure_mistral.type == "azure_openai"
    assert azure_mistral.api_key_env == "AZURE_FOUNDRY_API_KEY"
    assert azure_mistral.tier == 3
    assert azure_mistral.base_url == "https://disabled.services.ai.azure.com"
    assert azure_mistral.models == ["Mistral-Large-3"]
    # api_version rides in via extra-allow, so load_config succeeds without
    # it and the loss would only surface as a startup skip-warning; pin it.
    assert (azure_mistral.model_extra or {}).get("api_version") == "2024-10-21"

    # The parsed ``tier:`` FIELD (asserted above) is only resolution step 4;
    # the example ships ``inference_tiers.defaults.anthropic: 4`` ACTIVE
    # (step 3), which would shadow azure-claude's tier 3 without the
    # ``overrides: azure-claude: 3`` entry (step 2). Assert the DERIVED
    # runtime tier — the value stamped on responses, the routing log, and
    # checked by ``tier_policy.privileged_minimum_tier: 3``.
    from app.router import derive_routed_inference_tier

    for provider in (azure_openai, azure_claude, azure_mistral):
        assert (
            derive_routed_inference_tier(
                provider=provider,
                native_model=provider.models[0],
                inference_tiers=config.inference_tiers,
            )
            == 3
        ), f"{provider.name} must derive runtime tier 3 (enterprise Azure posture)"


@pytest.mark.unit
def test_anonymization_config_rejects_non_int_tiers() -> None:
    """``apply_at_tiers`` must be ``list[int]``; bad values raise."""

    from pydantic import ValidationError

    from app.config import AnonymizationConfig

    # Valid (default) — empty tiers list.
    AnonymizationConfig()
    # Valid — int list.
    cfg = AnonymizationConfig(apply_at_tiers=[3, 4, 5])
    assert cfg.apply_at_tiers == [3, 4, 5]
    # Tier out of [1,5] range surfaces as ValidationError.
    with pytest.raises(ValidationError):
        AnonymizationConfig(apply_at_tiers=[0, 1])
    with pytest.raises(ValidationError):
        AnonymizationConfig(apply_at_tiers=[1, 6])


@pytest.mark.unit
def test_citation_engine_config_default_is_fast() -> None:
    """An omitted ``citation_engine:`` block still yields the sensible default."""

    from app.config import CitationEngineConfig

    assert CitationEngineConfig().judge_model == "fast"
    assert CitationEngineConfig(judge_model="smart").judge_model == "smart"


@pytest.mark.unit
def test_citation_engine_config_rejects_empty_judge_model() -> None:
    """``judge_model`` must be a non-empty string."""

    from pydantic import ValidationError

    from app.config import CitationEngineConfig

    with pytest.raises(ValidationError):
        CitationEngineConfig(judge_model="")


@pytest.mark.unit
def test_load_config_alias_payload(example_env: None) -> None:
    """``GET /v1/models`` payload exposes the configured aliases."""

    config = load_config(EXAMPLE_CONFIG)
    payload = config.to_models_payload()

    assert payload["object"] == "list"
    ids = [entry["id"] for entry in payload["data"]]
    assert "smart" in ids
    assert "fast" in ids
    for entry in payload["data"]:
        assert entry["object"] == "model"
        assert entry["owned_by"] == "lq-ai-gateway"


# --- load_config: failure modes ----------------------------------------------


@pytest.mark.unit
def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigLoadError, match="not found"):
        load_config(tmp_path / "does-not-exist.yaml")


@pytest.mark.unit
def test_load_config_invalid_yaml_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("server:\n  port: : :\n", encoding="utf-8")
    with pytest.raises(ConfigLoadError, match="not valid YAML"):
        load_config(bad)


@pytest.mark.unit
def test_load_config_empty_file_raises(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ConfigLoadError, match="empty"):
        load_config(empty)


@pytest.mark.unit
def test_load_config_top_level_must_be_mapping(tmp_path: Path) -> None:
    listy = tmp_path / "listy.yaml"
    listy.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(ConfigLoadError, match="mapping"):
        load_config(listy)


@pytest.mark.unit
def test_load_config_unknown_alias_provider_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "gw.yaml"
    cfg.write_text(
        """
providers:
  - name: anthropic-prod
    type: anthropic
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
    tier: 4
    models: [claude-opus-4-7]
model_aliases:
  smart:
    primary: {provider: typo-prod, model: claude-opus-4-7}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError, match="typo-prod"):
        load_config(cfg)


@pytest.mark.unit
def test_load_config_invalid_tier_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "gw.yaml"
    cfg.write_text(
        """
providers:
  - name: anthropic-prod
    type: anthropic
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
    tier: 7
    models: [claude-opus-4-7]
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError, match="tier"):
        load_config(cfg)


@pytest.mark.unit
def test_load_config_empty_allowed_tiers_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "gw.yaml"
    cfg.write_text(
        """
providers: []
tier_policy:
  allowed_tiers_global: []
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError, match="allowed_tiers_global"):
        load_config(cfg)


# --- Direct schema sanity checks --------------------------------------------


@pytest.mark.unit
def test_model_target_requires_provider_and_model() -> None:
    target = ModelTarget(provider="x", model="y")
    assert target.provider == "x"
    assert target.model == "y"


# --- inference_tiers (B4) ----------------------------------------------------


@pytest.mark.unit
def test_load_config_parses_inference_tiers_block(example_env: None) -> None:
    """The example file's ``inference_tiers.defaults`` block loads."""

    config = load_config(EXAMPLE_CONFIG)
    assert config.inference_tiers.defaults["anthropic"] == 4
    assert config.inference_tiers.defaults["ollama"] == 1


@pytest.mark.unit
def test_load_config_invalid_inference_tier_default_rejected(tmp_path: Path) -> None:
    """A typo in ``inference_tiers.defaults`` (unknown provider type) fails."""

    cfg = tmp_path / "gw.yaml"
    cfg.write_text(
        """
providers:
  - name: anthropic-prod
    type: anthropic
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
    tier: 4
    models: [claude-opus-4-7]
inference_tiers:
  defaults:
    anthropc: 4   # typo
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError):
        load_config(cfg)


@pytest.mark.unit
def test_load_config_inference_tiers_value_out_of_range_rejected(tmp_path: Path) -> None:
    """Tier values outside 1..5 are rejected at load."""

    cfg = tmp_path / "gw.yaml"
    cfg.write_text(
        """
providers:
  - name: anthropic-prod
    type: anthropic
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
    tier: 4
    models: [claude-opus-4-7]
inference_tiers:
  defaults:
    anthropic: 9
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigLoadError):
        load_config(cfg)
