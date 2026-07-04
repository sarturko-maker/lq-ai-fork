"""Guard + behaviour tests for the operator tenant-setup wizard (SETUP-2).

`scripts/setup-tenant.sh` renders a hosted tenant's node-side artifacts from a
non-secret manifest + secrets supplied by the environment. These tests drive the
script as a subprocess (the way an operator does) and assert the SETUP-2 §9 gate:

* the rendered .env.prod carries EVERY ${VAR:?} the prod compose requires and no
  leftover REPLACE_ME placeholder;
* gateway.yaml parses, has exactly the Anthropic provider, carries NO key
  material (api_key_env indirection), and names no PRC provider;
* the fence holds — a manifest carrying a secret, an uncompiled DNS provider, a
  non-SHA image tag, or an unforced overwrite are all REFUSED;
* the VALUE fence holds (SETUP-2 review) — shell metacharacters, malformed
  emails/ports/recipients, and a wildcard origin are refused before anything is
  written (manifest values reach a root-sourced env file via the backup cron);
* secrets end up in .env.prod (chmod-600, node-only) and NEVER in gateway.yaml;
* SETUP-3b (ADR-F061 addendum D7): the handover is email-first — with SMTP
  configured the wizard POSTs /auth/password-reset-request for ADMIN_EMAIL and
  NEVER scrapes or prints the bootstrap password; without SMTP it keeps the
  log-scrape print, explicitly labelled as the fallback. The deploy-path tests
  shim `docker` and `curl` on PATH (argv logged to WIZARD_SHIM_LOG) so no real
  docker or network is touched;
* SETUP-3b: optional OPERATOR_EMAIL → FIRST_RUN_OPERATOR_EMAIL in .env.prod
  when set, omitted entirely when empty; same email/charset fences as
  ADMIN_EMAIL.

Style mirrors test_env_prod_example.py: same repo-root anchor, same compose
${VAR:?} parse, stdlib only + pytest + pyyaml (already an api dep).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "setup-tenant.sh"
_PROD_COMPOSE = _REPO_ROOT / "docker-compose.prod.yml"

# Distinctive fake secret values so we can prove where each one does (.env.prod)
# and does NOT (gateway.yaml, terminal) end up. None is a real credential.
_FAKE_SECRETS = {
    "LQ_AI_DNS_API_TOKEN": "faketok.deadbeefsecret",
    "S3_ACCESS_KEY": "FAKE3ACCESSKEYVALUE",
    "S3_SECRET_KEY": "fake3secretkeyvalue",
    "ANTHROPIC_API_KEY": "sk-ant-FAKEwizardkey0001",
}

# Skip cleanly if the shell toolchain isn't present (the guard runs in the dev
# image where both exist; a bare checkout without bash/openssl shouldn't error).
_TOOLCHAIN_OK = bool(shutil.which("bash")) and bool(shutil.which("openssl"))
pytestmark = pytest.mark.skipif(
    not _TOOLCHAIN_OK, reason="setup-tenant.sh needs bash + openssl on PATH"
)


def _required_compose_vars() -> set[str]:
    """Every ${VAR:?}-required var in the prod compose (guard-test parse)."""
    body = "\n".join(
        ln for ln in _PROD_COMPOSE.read_text().splitlines() if not ln.lstrip().startswith("#")
    )
    return set(re.findall(r"\$\{([A-Z0-9_]+):\?", body))


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip()
    return out


def _manifest_text(**overrides: str) -> str:
    fields = {
        "TENANT_SLUG": "acme",
        "PUBLIC_HOST": "acme.example.com",
        "DNS_PROVIDER": "ionos",
        "ACME_EMAIL": "ops@acme.example.com",
        "S3_ENDPOINT_URL": "https://s3.example.com",
        "S3_REGION": "de",
        "S3_BUCKET": "lq-ai-acme",
        "ADMIN_EMAIL": "admin@acme.example.com",
        "IMAGE_TAG": "sha-abc1234",
        "NODE_PROFILE": "reduced",
        "MODEL_PROVIDER": "anthropic",
        "AGE_RECIPIENT": "age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqsxxxxx",
        "BACKUP_DEADMAN_URL": "https://hc.example.com/ping/backup",
    }
    fields.update(overrides)
    return "\n".join(f"{k}={v}" for k, v in fields.items()) + "\n"


def _run(
    manifest: Path,
    out_dir: Path,
    *extra: str,
    secrets: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SMTP_", "ANTHROPIC_"))}
    env.update(_FAKE_SECRETS if secrets is None else secrets)
    return subprocess.run(
        ["bash", str(_SCRIPT), "--manifest", str(manifest), "--out-dir", str(out_dir), *extra],
        capture_output=True,
        text=True,
        env=env,
        # No TTY on stdin ⇒ the wizard's interactive secret prompts are skipped
        # (deterministic: a missing env secret dies instead of blocking on read).
        stdin=subprocess.DEVNULL,
        timeout=120,
    )


def _render(tmp_path: Path, **manifest_overrides: str) -> Path:
    """Real (non-dry-run) render into a fresh out-dir; returns the out-dir."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(**manifest_overrides))
    out_dir = tmp_path / "out"
    proc = _run(manifest, out_dir, "--no-deploy")
    assert proc.returncode == 0, f"render failed:\n{proc.stdout}\n{proc.stderr}"
    return out_dir


# --------------------------------------------------------------------------- #
# Render success path
# --------------------------------------------------------------------------- #
def test_script_exists_and_parses() -> None:
    assert _SCRIPT.is_file(), "scripts/setup-tenant.sh must exist"
    syntax = subprocess.run(["bash", "-n", str(_SCRIPT)], capture_output=True, text=True)
    assert syntax.returncode == 0, f"bash -n failed: {syntax.stderr}"


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text())
    out_dir = tmp_path / "out"
    proc = _run(manifest, out_dir, "--no-deploy", "--dry-run")
    assert proc.returncode == 0, proc.stderr
    assert not out_dir.exists(), "dry-run must not create the out-dir or any artifact"


def test_env_prod_covers_every_required_compose_var(tmp_path: Path) -> None:
    """(a) rendered .env.prod carries every ${VAR:?} the prod compose requires."""
    out_dir = _render(tmp_path)
    env = _parse_env(out_dir / ".env.prod")
    missing = sorted(_required_compose_vars() - set(env))
    assert not missing, f".env.prod is missing required compose vars: {missing}"


def test_no_replace_me_placeholder_remains(tmp_path: Path) -> None:
    """(b) a rendered .env.prod must have no REPLACE_ME left in it."""
    out_dir = _render(tmp_path)
    text = (out_dir / ".env.prod").read_text()
    assert "REPLACE_ME" not in text, "rendered .env.prod still contains a REPLACE_ME placeholder"


def test_rendered_files_are_chmod_600(tmp_path: Path) -> None:
    out_dir = _render(tmp_path)
    for name in (".env.prod", "gateway.yaml"):
        mode = (out_dir / name).stat().st_mode & 0o777
        assert mode == 0o600, f"{name} must be chmod 600, got {oct(mode)}"


def test_gateway_yaml_is_anthropic_only_and_keyless(tmp_path: Path) -> None:
    """(c) gateway.yaml parses, has exactly the Anthropic provider, no key material."""
    out_dir = _render(tmp_path)
    gw_text = (out_dir / "gateway.yaml").read_text()
    doc = yaml.safe_load(gw_text)

    providers = doc["providers"]
    assert len(providers) == 1, f"tenant seed must have exactly one provider, got {len(providers)}"
    prov = providers[0]
    assert prov["type"] == "anthropic"
    # api_key_env indirection only — never an inline key field.
    assert prov["api_key_env"] == "ANTHROPIC_API_KEY"
    assert "api_key" not in prov and "api_key_encrypted" not in prov

    aliases = doc["model_aliases"]
    assert {"smart", "fast", "budget"} <= set(aliases), f"missing core aliases: {aliases.keys()}"

    # No PRC provider anywhere (ADR-F058 fence), case-insensitive.
    assert not re.search(r"minimax|deepseek", gw_text, re.IGNORECASE), "PRC provider in tenant seed"


def test_secrets_land_in_env_prod_never_in_gateway(tmp_path: Path) -> None:
    """(c) fake secret values PRESENT in .env.prod, ABSENT from gateway.yaml."""
    out_dir = _render(tmp_path)
    env_text = (out_dir / ".env.prod").read_text()
    gw_text = (out_dir / "gateway.yaml").read_text()
    for name, value in _FAKE_SECRETS.items():
        assert value in env_text, f"{name} value should be written into .env.prod"
        assert value not in gw_text, f"{name} value LEAKED into gateway.yaml (must be keyless)"


def test_dns_records_names_the_host(tmp_path: Path) -> None:
    """(h) dns-records.txt names the tenant host."""
    out_dir = _render(tmp_path)
    dns = (out_dir / "dns-records.txt").read_text()
    assert "acme.example.com" in dns
    assert "ionos" in dns  # the provider reminder


def test_backup_cron_is_generated(tmp_path: Path) -> None:
    out_dir = _render(tmp_path)
    cron = (out_dir / "cron.d-lq-ai-backup").read_text()
    assert "17 3 * * *" in cron
    assert "backup.sh" in cron


# --------------------------------------------------------------------------- #
# Fence / refusal paths
# --------------------------------------------------------------------------- #
def test_manifest_with_secret_is_refused(tmp_path: Path) -> None:
    """(d) a manifest that carries a secret-suffixed key with a value is refused."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text() + "ANTHROPIC_API_KEY=sk-should-not-be-here\n")
    out_dir = tmp_path / "out"
    proc = _run(manifest, out_dir, "--no-deploy", "--dry-run")
    assert proc.returncode != 0
    assert "secret" in proc.stderr.lower()
    assert not out_dir.exists()


def test_invalid_dns_provider_is_refused(tmp_path: Path) -> None:
    """(e) an uncompiled DNS provider (cloudflare) is refused."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(DNS_PROVIDER="cloudflare"))
    proc = _run(manifest, tmp_path / "out", "--no-deploy", "--dry-run")
    assert proc.returncode != 0
    assert "cloudflare" in proc.stderr.lower()


def test_invalid_image_tag_is_refused(tmp_path: Path) -> None:
    """(f) a non-SHA image tag (never :main) is refused."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(IMAGE_TAG="main"))
    proc = _run(manifest, tmp_path / "out", "--no-deploy", "--dry-run")
    assert proc.returncode != 0
    assert "sha-" in proc.stderr.lower()


def test_invalid_slug_is_refused(tmp_path: Path) -> None:
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(TENANT_SLUG="Acme_Corp"))  # uppercase + underscore
    proc = _run(manifest, tmp_path / "out", "--no-deploy", "--dry-run")
    assert proc.returncode != 0
    assert "tenant_slug" in proc.stderr.lower()


def test_existing_env_prod_not_overwritten_without_force(tmp_path: Path) -> None:
    """(g) an existing .env.prod is preserved unless --force is given."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text())
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    sentinel = "PRE_EXISTING_DO_NOT_CLOBBER=1\n"
    (out_dir / ".env.prod").write_text(sentinel)

    proc = _run(manifest, out_dir, "--no-deploy")
    assert proc.returncode != 0, "must refuse to overwrite an existing .env.prod"
    assert (out_dir / ".env.prod").read_text() == sentinel, "existing .env.prod was clobbered"

    forced = _run(manifest, out_dir, "--no-deploy", "--force")
    assert forced.returncode == 0, f"--force render failed:\n{forced.stderr}"
    assert (out_dir / ".env.prod").read_text() != sentinel, "--force should have rewritten it"


def test_missing_secret_env_is_refused(tmp_path: Path) -> None:
    """A required secret absent from the environment (no TTY prompt) is refused."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text())
    incomplete = dict(_FAKE_SECRETS)
    del incomplete["ANTHROPIC_API_KEY"]
    proc = _run(manifest, tmp_path / "out", "--no-deploy", secrets=incomplete)
    assert proc.returncode != 0
    assert "anthropic_api_key" in proc.stderr.lower()


# --------------------------------------------------------------------------- #
# Value fences (SETUP-2 review, SHOULD_FIX 2 / NIT 3 / NIT 5) — every manifest
# value lands in a ROOT-SOURCED env file (the backup cron does
# `set -a; . .env.prod`), so shell metacharacters are latent root code exec.
# --------------------------------------------------------------------------- #
def test_command_substitution_value_is_refused(tmp_path: Path) -> None:
    """A value carrying $(...) must die at the generic charset fence."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(S3_REGION="de$(id)"))
    proc = _run(manifest, tmp_path / "out", "--no-deploy", "--dry-run")
    assert proc.returncode != 0
    assert "s3_region" in proc.stderr.lower()
    assert not (tmp_path / "out").exists()


def test_email_with_space_is_refused(tmp_path: Path) -> None:
    """ADMIN_EMAIL is customer-originated — a space (word-splitting in a sourced
    file) must be refused."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(ADMIN_EMAIL="admin @acme.example.com"))
    proc = _run(manifest, tmp_path / "out", "--no-deploy", "--dry-run")
    assert proc.returncode != 0
    assert "admin_email" in proc.stderr.lower()


def test_nonnumeric_smtp_port_is_refused(tmp_path: Path) -> None:
    """config.py's smtp_port is an int — a non-numeric value would crash-loop
    the api at boot; the wizard must catch it up front."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(SMTP_PORT="abc"))
    proc = _run(manifest, tmp_path / "out", "--no-deploy", "--dry-run")
    assert proc.returncode != 0
    assert "smtp_port" in proc.stderr.lower()


def test_garbage_age_recipient_is_refused(tmp_path: Path) -> None:
    """AGE_RECIPIENT is a full-shape check (age1 + bech32), not prefix-only."""
    for bad in ("age1short", "agekey-not-a-recipient"):
        manifest = tmp_path / "tenant.conf"
        manifest.write_text(_manifest_text(AGE_RECIPIENT=bad))
        proc = _run(manifest, tmp_path / "out", "--no-deploy", "--dry-run")
        assert proc.returncode != 0, f"AGE_RECIPIENT={bad!r} should be refused"
        assert "age_recipient" in proc.stderr.lower()


def test_leading_hyphen_slug_is_refused(tmp_path: Path) -> None:
    """'-x' would parse as a docker flag downstream; slugs start/end alnum."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(TENANT_SLUG="-x"))
    proc = _run(manifest, tmp_path / "out", "--no-deploy", "--dry-run")
    assert proc.returncode != 0
    assert "tenant_slug" in proc.stderr.lower()


def test_wildcard_host_requires_concrete_public_origin(tmp_path: Path) -> None:
    """A wildcard PUBLIC_HOST must not leak '*' into LQ_AI_PUBLIC_ORIGIN
    (Collabora's server_name) — it requires an explicit concrete PUBLIC_ORIGIN."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(PUBLIC_HOST="*.acme.example.com"))
    proc = _run(manifest, tmp_path / "out-a", "--no-deploy", "--dry-run")
    assert proc.returncode != 0
    assert "public_origin" in proc.stderr.lower()

    out_dir = _render(
        tmp_path, PUBLIC_HOST="*.acme.example.com", PUBLIC_ORIGIN="app.acme.example.com"
    )
    env = _parse_env(out_dir / ".env.prod")
    assert env["LQ_AI_PUBLIC_HOST"] == "*.acme.example.com"
    assert env["LQ_AI_PUBLIC_ORIGIN"] == "app.acme.example.com"


def test_interactive_mode_saves_secretfree_manifest_0600(tmp_path: Path) -> None:
    """Interactive answers become a repeatable, chmod-600, secret-free manifest."""
    answers = (
        "\n".join(
            [
                "beta",  # slug
                "beta.example.com",  # host (concrete: no origin prompt)
                "ionos",  # dns provider
                "ops@beta.example.com",  # acme email
                "https://s3.example.com",  # s3 endpoint
                "de",  # s3 region
                "",  # s3 bucket (default)
                "admin@beta.example.com",  # admin email
                "",  # operator email (SETUP-3b — skip: no operator account)
                "",  # smtp host (skip smtp block)
                "sha-def5678",  # image tag
                "full",  # node profile
                "anthropic",  # model provider
                "age1" + "q" * 40,  # age recipient
                "",  # backup dead-man
                "",  # restore dead-man
            ]
        )
        + "\n"
    )
    save = tmp_path / "tenant-beta.conf"
    out_dir = tmp_path / "out"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SMTP_", "ANTHROPIC_"))}
    env.update(_FAKE_SECRETS)
    proc = subprocess.run(
        [
            "bash",
            str(_SCRIPT),
            "--out-dir",
            str(out_dir),
            "--save-manifest",
            str(save),
            "--no-deploy",
        ],
        capture_output=True,
        text=True,
        env=env,
        input=answers,
        timeout=120,
    )
    assert proc.returncode == 0, f"interactive run failed:\n{proc.stdout}\n{proc.stderr}"
    assert save.is_file(), "interactive mode must write the repeatable manifest"
    mode = save.stat().st_mode & 0o777
    assert mode == 0o600, f"saved manifest must be chmod 600, got {oct(mode)}"
    text = save.read_text()
    assert "TENANT_SLUG=beta" in text
    assert "OPERATOR_EMAIL=" in text  # the key is persisted even when blank
    for value in _FAKE_SECRETS.values():
        assert value not in text, "secret value leaked into the saved manifest"


# --------------------------------------------------------------------------- #
# SETUP-3b — OPERATOR_EMAIL → FIRST_RUN_OPERATOR_EMAIL (ADR-F061)
# --------------------------------------------------------------------------- #
def test_operator_email_written_when_set(tmp_path: Path) -> None:
    out_dir = _render(tmp_path, OPERATOR_EMAIL="operator@platform.example.com")
    env = _parse_env(out_dir / ".env.prod")
    assert env["FIRST_RUN_OPERATOR_EMAIL"] == "operator@platform.example.com"


def test_operator_email_omitted_entirely_when_unset(tmp_path: Path) -> None:
    """No OPERATOR_EMAIL ⇒ no FIRST_RUN_OPERATOR_EMAIL key at all (self-host
    semantics: an unset var means no operator account is ever minted)."""
    out_dir = _render(tmp_path)
    env = _parse_env(out_dir / ".env.prod")
    assert "FIRST_RUN_OPERATOR_EMAIL" not in env


def test_operator_email_charset_fence_applies(tmp_path: Path) -> None:
    """The generic root-sourced-env-file charset fence covers the new field."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(OPERATOR_EMAIL="op$(id)@acme.example.com"))
    proc = _run(manifest, tmp_path / "out", "--no-deploy", "--dry-run")
    assert proc.returncode != 0
    assert "operator_email" in proc.stderr.lower()
    assert not (tmp_path / "out").exists()


def test_operator_email_shape_check_applies(tmp_path: Path) -> None:
    """A charset-clean but non-email value is refused by the EMAIL_RE check."""
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(OPERATOR_EMAIL="not-an-email"))
    proc = _run(manifest, tmp_path / "out", "--no-deploy", "--dry-run")
    assert proc.returncode != 0
    assert "operator_email" in proc.stderr.lower()


# --------------------------------------------------------------------------- #
# SETUP-3b — handover (ADR-F061 addendum D7): email-first with SMTP, log-scrape
# fallback without. The deploy path is exercised with `docker` + `curl` shims
# on PATH so no real docker/network is touched; each shim appends its argv to
# WIZARD_SHIM_LOG so the tests can assert exactly what the wizard invoked.
# --------------------------------------------------------------------------- #
_FAKE_BOOTSTRAP_PW = "fake-bootstrap-pw-e2e"


def _write_shims(shim_dir: Path) -> None:
    shim_dir.mkdir(parents=True, exist_ok=True)
    docker = shim_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        'printf \'docker %s\\n\' "$*" >> "$WIZARD_SHIM_LOG"\n'
        'case "$*" in\n'
        # deploy.sh reads the public host back out of the caddy service.
        '  *"printenv LQ_AI_PUBLIC_HOST"*) echo "acme.example.com" ;;\n'
        # the SMTP-off fallback greps this exact prefix from the api log.
        f'  *"logs api"*) echo "First-run admin password (record it now and '
        f'rotate on first login): {_FAKE_BOOTSTRAP_PW}" ;;\n'
        "esac\n"
        "exit 0\n"
    )
    docker.chmod(0o755)
    curl = shim_dir / "curl"
    curl.write_text(
        '#!/usr/bin/env bash\nprintf \'curl %s\\n\' "$*" >> "$WIZARD_SHIM_LOG"\nexit 0\n'
    )
    curl.chmod(0o755)


def _run_with_deploy(tmp_path: Path, *, smtp: bool) -> tuple[subprocess.CompletedProcess[str], str]:
    """Full run (deploy enabled) against the shims; returns (proc, shim log)."""
    overrides: dict[str, str] = {}
    secrets = dict(_FAKE_SECRETS)
    if smtp:
        overrides.update(
            SMTP_HOST="smtp.example.com",
            SMTP_FROM="noreply@acme.example.com",
            SMTP_USERNAME="mailer",
        )
        secrets["SMTP_PASSWORD"] = "fake-smtp-password"
    manifest = tmp_path / "tenant.conf"
    manifest.write_text(_manifest_text(**overrides))
    out_dir = tmp_path / "out"
    shim_dir = tmp_path / "shims"
    _write_shims(shim_dir)
    shim_log = tmp_path / "shim.log"
    shim_log.write_text("")

    env = {k: v for k, v in os.environ.items() if not k.startswith(("SMTP_", "ANTHROPIC_"))}
    env.update(secrets)
    env["PATH"] = f"{shim_dir}:{env.get('PATH', '')}"
    env["WIZARD_SHIM_LOG"] = str(shim_log)
    proc = subprocess.run(
        ["bash", str(_SCRIPT), "--manifest", str(manifest), "--out-dir", str(out_dir)],
        capture_output=True,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=180,
    )
    return proc, shim_log.read_text()


def test_smtp_on_handover_sends_reset_request_and_never_prints_password(
    tmp_path: Path,
) -> None:
    """D7: SMTP configured ⇒ the wizard fires POST /auth/password-reset-request
    for ADMIN_EMAIL against the public origin, and the bootstrap password is
    neither scraped from the log nor printed anywhere."""
    proc, shim_log = _run_with_deploy(tmp_path, smtp=True)
    assert proc.returncode == 0, f"deploy run failed:\n{proc.stdout}\n{proc.stderr}"

    # The handover request was made, for the right address, at the right URL.
    assert "https://acme.example.com/api/v1/auth/password-reset-request" in shim_log
    assert "admin@acme.example.com" in shim_log
    assert "Handover email sent" in proc.stdout

    # The password never transits the operator's terminal on this branch —
    # and the wizard never even reads the api log.
    combined = proc.stdout + proc.stderr
    assert _FAKE_BOOTSTRAP_PW not in combined
    assert "First-run admin password" not in combined
    assert "logs api" not in shim_log


def test_smtp_off_handover_keeps_log_scrape_fallback(tmp_path: Path) -> None:
    """D7 fallback: no SMTP ⇒ today's log-scrape print, explicitly labelled,
    and no reset-request call is fired."""
    proc, shim_log = _run_with_deploy(tmp_path, smtp=False)
    assert proc.returncode == 0, f"deploy run failed:\n{proc.stdout}\n{proc.stderr}"

    assert "SMTP is not configured" in proc.stdout
    assert _FAKE_BOOTSTRAP_PW in proc.stdout
    assert "password-reset-request" not in shim_log
