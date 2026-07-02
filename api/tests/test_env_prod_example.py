"""Guard: .env.prod.example carries placeholders only, and stays in sync with the
prod compose's required vars (SAAS-3, ADR-F060 D6).

The public repo must never ship a real secret (the .env.bak leak is the standing
lesson). This test fails if a secret-shaped value looks real, if any value is a
high-entropy blob, or if the example drifts from docker-compose.prod.yml's
required ${VAR:?} set.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE = _REPO_ROOT / ".env.prod.example"
_PROD_COMPOSE = _REPO_ROOT / "docker-compose.prod.yml"

# Keys whose value must be empty or an obvious placeholder — never a real secret.
# Suffix-anchored so config knobs that merely CONTAIN the word (e.g.
# JWT_ACCESS_TOKEN_TTL_SECONDS, RATE_LIMIT_CHANGE_PASSWORD_ACCOUNT_PER_WINDOW —
# both numbers) don't trip the guard.
_SECRET_KEY_RE = re.compile(r"(_PASSWORD$|_SECRET$|_TOKEN$|_KEY$|APPLICATION_CREDENTIALS$)")
# A value that looks like a real credential: a long unbroken hex/base64 run.
_HIGH_ENTROPY_RE = re.compile(r"^[A-Za-z0-9+/_-]{32,}={0,2}$")
# Obvious placeholders / safe example values that _HIGH_ENTROPY_RE might catch.
_ALLOWED_PLACEHOLDER = re.compile(r"REPLACE_ME|^age1REPLACE_ME")


def _parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip()
    return out


def test_env_prod_example_exists() -> None:
    assert _EXAMPLE.is_file(), ".env.prod.example must exist for the hosted deploy"


def test_no_real_secrets() -> None:
    env = _parse(_EXAMPLE)
    assert env, ".env.prod.example parsed to zero KEY=value lines"
    for key, val in env.items():
        if val == "" or _ALLOWED_PLACEHOLDER.search(val):
            continue
        if _SECRET_KEY_RE.search(key):
            pytest.fail(f"{key} looks like it carries a real secret: {val!r}")
        assert not _HIGH_ENTROPY_RE.match(val), (
            f"{key}={val!r} looks like a high-entropy secret; use a REPLACE_ME placeholder"
        )


def test_covers_required_compose_vars() -> None:
    """Every ${VAR:?} required by the prod compose must appear in the example."""
    # Strip full-line comments first — the compose header documents the ${VAR:?}
    # convention literally, and that doc reference is not a real required var.
    body = "\n".join(
        ln for ln in _PROD_COMPOSE.read_text().splitlines() if not ln.lstrip().startswith("#")
    )
    required = set(re.findall(r"\$\{([A-Z0-9_]+):\?", body))
    assert required, "expected to find required ${VAR:?} vars in docker-compose.prod.yml"
    have = set(_parse(_EXAMPLE))
    missing = sorted(required - have)
    assert not missing, f".env.prod.example is missing required vars: {missing}"
