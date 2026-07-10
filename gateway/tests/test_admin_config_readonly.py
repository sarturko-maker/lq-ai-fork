"""HS-2 (CLEAN-4): gateway config read-only mode.

When the gateway config is mounted read-only (an immutable Kubernetes ConfigMap
across replicas), the admin WRITE endpoints must refuse mutations with 409
instead of failing an ``os.replace`` on the ``:ro`` mount or diverging per-pod.
The mode is set on ``app.state.config_read_only`` at lifespan from the
``LQ_AI_GATEWAY_CONFIG_READONLY`` env.

Mirrors ``tests/test_admin_aliases.py``'s temp-config app fixture so writes
never touch the repo's source-controlled ``gateway.yaml.example``.
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api import admin_router
from app.config_holder import MutableConfigHolder
from app.config_loader import load_config
from app.errors import LQAIError
from app.main import CONFIG_READONLY_ENV, _config_read_only

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = REPO_ROOT / "gateway.yaml.example"


@pytest.fixture
def tmp_gateway_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AZURE_OPENAI_RESOURCE", "test-openai")
    monkeypatch.setenv("LQ_AI_VERSION", "0.1.0-test")
    target = tmp_path / "gateway.yaml"
    shutil.copy(EXAMPLE_CONFIG, target)
    return target


def _build_app(config_path: Path, *, read_only: bool) -> FastAPI:
    config = load_config(config_path)
    holder = MutableConfigHolder(config, config_path=config_path)
    app = FastAPI()
    app.state.config = config
    app.state.config_holder = holder
    app.state.config_read_only = read_only
    app.include_router(admin_router)

    @app.exception_handler(LQAIError)
    async def _handler(_request: object, exc: LQAIError) -> JSONResponse:
        return JSONResponse(status_code=exc.effective_http_status, content=exc.to_envelope())

    return app


async def _client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest_asyncio.fixture
async def readonly_client(tmp_gateway_config: Path) -> AsyncIterator[AsyncClient]:
    async for c in _client(_build_app(tmp_gateway_config, read_only=True)):
        yield c


@pytest_asyncio.fixture
async def writable_client(tmp_gateway_config: Path) -> AsyncIterator[AsyncClient]:
    async for c in _client(_build_app(tmp_gateway_config, read_only=False)):
        yield c


# Every config-mutating admin request: (method, path, json-or-None). "smart" and
# "anthropic-prod" exist in gateway.yaml.example; the read-only guard fires
# before any existence/precondition check, so these need only be structurally
# valid (Pydantic runs first).
_MUTATIONS = [
    (
        "post",
        "/admin/v1/aliases",
        {
            "name": "ro-new",
            "provider": "anthropic-prod",
            "model": "claude-opus-4-7",
            "fallback": [],
        },
    ),
    (
        "patch",
        "/admin/v1/aliases/smart",
        {"provider": "anthropic-prod", "model": "claude-opus-4-7"},
    ),
    ("delete", "/admin/v1/aliases/smart", None),
    ("patch", "/admin/v1/tier-config", {}),
    ("post", "/admin/v1/provider-keys", {"provider": "anthropic-prod", "api_key": "sk-test"}),
    ("patch", "/admin/v1/provider-keys/anthropic-prod", {"api_key": "sk-test"}),
    ("delete", "/admin/v1/provider-keys/anthropic-prod", None),
]


@pytest.mark.unit
@pytest.mark.parametrize(("method", "path", "payload"), _MUTATIONS)
async def test_mutation_blocked_when_read_only(
    readonly_client: AsyncClient, method: str, path: str, payload: dict | None
) -> None:
    """Every config-write endpoint returns 409 config_read_only in read-only mode."""

    kwargs = {"json": payload} if payload is not None else {}
    resp = await getattr(readonly_client, method)(path, **kwargs)
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "config_read_only"


@pytest.mark.unit
async def test_read_only_leaves_config_file_untouched(
    readonly_client: AsyncClient, tmp_gateway_config: Path
) -> None:
    """A blocked write never reaches the writer — the on-disk file is byte-identical."""

    before = tmp_gateway_config.read_bytes()
    resp = await readonly_client.post(
        "/admin/v1/aliases",
        json={
            "name": "ro-untouched",
            "provider": "anthropic-prod",
            "model": "claude-opus-4-7",
            "fallback": [],
        },
    )
    assert resp.status_code == 409
    assert tmp_gateway_config.read_bytes() == before


@pytest.mark.unit
async def test_reads_still_work_when_read_only(readonly_client: AsyncClient) -> None:
    """Read-only mode blocks only writes — GETs are unaffected."""

    resp = await readonly_client.get("/admin/v1/aliases")
    assert resp.status_code == 200
    assert "data" in resp.json()


@pytest.mark.unit
async def test_writes_allowed_when_not_read_only(writable_client: AsyncClient) -> None:
    """Regression: the guard must not block writes when read-only is off (default)."""

    resp = await writable_client.post(
        "/admin/v1/aliases",
        json={
            "name": "rw-ok",
            "provider": "anthropic-prod",
            "model": "claude-opus-4-7",
            "fallback": [],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "rw-ok"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("  yes  ", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("", False),
        ("nope", False),
    ],
)
def test_config_read_only_env_parsing(value: str, expected: bool) -> None:
    assert _config_read_only({CONFIG_READONLY_ENV: value}) is expected


@pytest.mark.unit
def test_config_read_only_absent_defaults_false() -> None:
    assert _config_read_only({}) is False
