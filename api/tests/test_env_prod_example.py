"""Guard: the committed env-file examples carry placeholders only, and stay in
sync with their compose files' required vars (SAAS-3, ADR-F060 D6; the private
profile's example is P-1, ADR-F070).

The public repo must never ship a real secret (the .env.bak leak is the standing
lesson). This test fails if a secret-shaped value looks real, if any value is a
high-entropy blob, or if an example drifts from its compose file's required
${VAR:?} set.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROD_EXAMPLE = _REPO_ROOT / ".env.prod.example"
_PRIVATE_EXAMPLE = _REPO_ROOT / ".env.private.example"
_PROD_COMPOSE = _REPO_ROOT / "docker-compose.prod.yml"
_PRIVATE_COMPOSE = _REPO_ROOT / "docker-compose.private.yml"

# Keys whose value must be empty or an obvious placeholder — never a real secret.
# Suffix-anchored so config knobs that merely CONTAIN the word (e.g.
# JWT_ACCESS_TOKEN_TTL_SECONDS, RATE_LIMIT_CHANGE_PASSWORD_ACCOUNT_PER_WINDOW —
# both numbers) don't trip the guard.
_SECRET_KEY_RE = re.compile(r"(_PASSWORD$|_SECRET$|_TOKEN$|_KEY$|APPLICATION_CREDENTIALS$)")
# A value that looks like a real credential: a long unbroken hex/base64 run.
_HIGH_ENTROPY_RE = re.compile(r"^[A-Za-z0-9+/_-]{32,}={0,2}$")
# Obvious placeholders / safe example values that _HIGH_ENTROPY_RE might catch.
_ALLOWED_PLACEHOLDER = re.compile(r"REPLACE_ME|^age1REPLACE_ME")

# The private profile satisfies the prod compose's parse-time ${VAR:?} public-edge
# vars with documented INERT placeholders (ADR-F070) — never read at runtime in
# that profile. Allowlisted by EXACT key+value pair (never a blanket key
# exemption): any changed value must re-justify itself here.
_INERT_PRIVATE_PLACEHOLDERS = frozenset(
    {
        ("LQ_AI_PUBLIC_HOST", "private.invalid"),
        ("LQ_AI_ACME_EMAIL", "unused@private.invalid"),
        ("LQ_AI_DNS_API_TOKEN", "unused"),
    }
)


def _parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip()
    return out


def _required_compose_vars(compose: Path) -> set[str]:
    """The ${VAR:?} vars a compose file refuses to parse without."""
    # Strip full-line comments first — the compose headers document the ${VAR:?}
    # convention literally, and that doc reference is not a real required var.
    body = "\n".join(
        ln for ln in compose.read_text().splitlines() if not ln.lstrip().startswith("#")
    )
    return set(re.findall(r"\$\{([A-Z0-9_]+):\?", body))


@pytest.mark.parametrize("example", [_PROD_EXAMPLE, _PRIVATE_EXAMPLE], ids=lambda p: p.name)
def test_env_example_exists(example: Path) -> None:
    assert example.is_file(), f"{example.name} must exist for the deploy paths"


@pytest.mark.parametrize(
    ("example", "inert_allowed"),
    [
        pytest.param(_PROD_EXAMPLE, frozenset(), id=_PROD_EXAMPLE.name),
        pytest.param(_PRIVATE_EXAMPLE, _INERT_PRIVATE_PLACEHOLDERS, id=_PRIVATE_EXAMPLE.name),
    ],
)
def test_no_real_secrets(example: Path, inert_allowed: frozenset[tuple[str, str]]) -> None:
    env = _parse(example)
    assert env, f"{example.name} parsed to zero KEY=value lines"
    for key, val in env.items():
        if val == "" or _ALLOWED_PLACEHOLDER.search(val):
            continue
        if (key, val) in inert_allowed:
            continue
        if _SECRET_KEY_RE.search(key):
            pytest.fail(f"{example.name}: {key} looks like it carries a real secret: {val!r}")
        assert not _HIGH_ENTROPY_RE.match(val), (
            f"{example.name}: {key}={val!r} looks like a high-entropy secret; "
            "use a REPLACE_ME placeholder"
        )


@pytest.mark.parametrize(
    ("example", "compose"),
    [
        pytest.param(_PROD_EXAMPLE, _PROD_COMPOSE, id="prod-example/prod-compose"),
        # The private profile composes BOTH files with ONE env file, so its
        # example must satisfy the prod compose's required set too.
        pytest.param(_PRIVATE_EXAMPLE, _PROD_COMPOSE, id="private-example/prod-compose"),
        pytest.param(_PRIVATE_EXAMPLE, _PRIVATE_COMPOSE, id="private-example/private-compose"),
    ],
)
def test_covers_required_compose_vars(example: Path, compose: Path) -> None:
    """Every ${VAR:?} required by the compose file must appear in the example."""
    required = _required_compose_vars(compose)
    assert required, f"expected to find required ${{VAR:?}} vars in {compose.name}"
    have = set(_parse(example))
    missing = sorted(required - have)
    assert not missing, f"{example.name} is missing required vars: {missing}"
