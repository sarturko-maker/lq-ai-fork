"""Integration tests for skill prompt assembly on /v1/chat/completions (C2).

Exercises the full request flow at the gateway layer:

1. Caller posts a chat completion with `lq_ai_skills` set.
2. The gateway fetches each skill from the (mocked) backend's
   internal-skills endpoint.
3. The assembler builds the system message; skill content is prepended.
4. The assembled request goes to the (mocked) Anthropic adapter.
5. The response carries `lq_ai_applied_skills`.

Both sides (backend internal-skills + Anthropic upstream) are
respx-mocked. The Anthropic mock captures the request body so we can
assert the gateway sent the assembled system message.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.clients.backend import (
    BackendClient,
    SkillCache,
    set_backend_client,
)
from app.routing_log import RecordingRoutingLogWriter

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = REPO_ROOT / "gateway.yaml.example"


@asynccontextmanager
async def _run_lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with app.router.lifespan_context(app):
        yield


# Fixed backend URL the BackendClient will dial; respx.mock matches it.
BACKEND_URL = "http://api.test"
GATEWAY_KEY = "test-gateway-key-correct-horse"


@pytest_asyncio.fixture
async def gateway_with_skill_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[FastAPI, RecordingRoutingLogWriter, BackendClient]]:
    """Bring up the gateway with a respx-mockable BackendClient for skills."""

    monkeypatch.setenv("GATEWAY_CONFIG_PATH", str(EXAMPLE_CONFIG))
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AZURE_OPENAI_RESOURCE", "test-openai")
    monkeypatch.setenv("LQ_AI_VERSION", "0.1.0-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
    monkeypatch.setenv("LQ_AI_API_URL", BACKEND_URL)
    monkeypatch.setenv("LQ_AI_GATEWAY_KEY", GATEWAY_KEY)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.main import app

    async with _run_lifespan(app):
        recorder = RecordingRoutingLogWriter()
        app.state.routing_log = recorder
        # Replace the lifespan-built BackendClient with one whose
        # underlying httpx client respx can intercept. respx mounts at
        # the *transport* layer, so we don't strictly need a fresh
        # client — but giving the test deterministic ownership lets
        # us reset the cache between tests cleanly.
        backend_client = BackendClient(
            base_url=BACKEND_URL,
            gateway_key=GATEWAY_KEY,
            cache=SkillCache(ttl_seconds=60.0),
        )
        app.state.backend_client = backend_client
        set_backend_client(backend_client)
        try:
            yield app, recorder, backend_client
        finally:
            await backend_client.aclose()
            set_backend_client(None)


@pytest_asyncio.fixture
async def http_client(
    gateway_with_skill_backend: tuple[FastAPI, RecordingRoutingLogWriter, BackendClient],
) -> AsyncIterator[tuple[AsyncClient, BackendClient]]:
    app, _recorder, backend = gateway_with_skill_backend
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, backend


# --- Mock helpers ------------------------------------------------------------


def _mock_backend_skill(
    name: str,
    *,
    body: str,
    inputs_yaml: str = "",
    reference: list[tuple[str, str]] | None = None,
) -> None:
    """Register a respx stub for `GET /api/v1/internal/skills/{name}`."""

    yaml_block = f"name: {name}\ndescription: ...\n"
    if inputs_yaml:
        yaml_block += inputs_yaml

    references = [{"path": path, "content": content} for (path, content) in (reference or [])]

    respx.get(f"{BACKEND_URL}/api/v1/internal/skills/{name}").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": name,
                "version": "1.0.0",
                "scope": "builtin",
                "title": name.title(),
                "description": f"Test skill {name}",
                "content_md": body,
                "content_yaml": yaml_block,
                "reference_files": references,
            },
        )
    )


# --- Tests -------------------------------------------------------------------


@pytest.mark.integration
@respx.mock
async def test_skill_assembly_prepends_system_message(
    http_client: tuple[AsyncClient, BackendClient],
) -> None:
    """A request with `lq_ai_skills` ends up with skill body in the system message."""

    client, _backend = http_client
    _mock_backend_skill(
        "alpha",
        body="# Alpha workflow\n\n1. Read the input.\n2. Output a report.",
    )
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg_c2_001",
                "model": "claude-opus-4-7",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 5},
            },
        )

    respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=_capture)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "smart",
            "messages": [{"role": "user", "content": "hello"}],
            "lq_ai_skills": ["alpha"],
        },
    )
    assert response.status_code == 200, response.text

    # The assembled system message reached Anthropic.
    body = captured["body"]
    assert isinstance(body, dict)
    system = body.get("system")
    assert isinstance(system, str)
    assert "Alpha workflow" in system
    assert "Read the input." in system

    # The response surfaces the applied-skills set.
    response_body = response.json()
    assert response_body.get("lq_ai_applied_skills") == ["alpha"]


@pytest.mark.integration
@respx.mock
async def test_skill_assembly_preserves_existing_system_message(
    http_client: tuple[AsyncClient, BackendClient],
) -> None:
    """Pre-existing system message is preserved (after a separator)."""

    client, _backend = http_client
    _mock_backend_skill("alpha", body="Alpha body")
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg_c2_002",
                "model": "claude-opus-4-7",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=_capture)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "smart",
            "messages": [
                {"role": "system", "content": "Be terse."},
                {"role": "user", "content": "hello"},
            ],
            "lq_ai_skills": ["alpha"],
        },
    )
    assert response.status_code == 200, response.text

    body = captured["body"]
    assert isinstance(body, dict)
    system = body["system"]
    assert isinstance(system, str)
    # Skill body comes first.
    assert "Alpha body" in system
    # Operator instruction is preserved after the separator.
    assert "Be terse." in system
    assert system.index("Alpha body") < system.index("Be terse.")


@pytest.mark.integration
@respx.mock
async def test_skill_assembly_with_input_substitution(
    http_client: tuple[AsyncClient, BackendClient],
) -> None:
    """`lq_ai_skill_inputs` bindings substitute into the body."""

    client, _backend = http_client
    _mock_backend_skill(
        "alpha",
        body="Review {{document}} from {{perspective}}.",
    )
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg_c2_003",
                "model": "claude-opus-4-7",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=_capture)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "smart",
            "messages": [{"role": "user", "content": "hello"}],
            "lq_ai_skills": ["alpha"],
            "lq_ai_skill_inputs": {"alpha": {"document": "the NDA", "perspective": "discloser"}},
        },
    )
    assert response.status_code == 200, response.text
    body = captured["body"]
    assert isinstance(body, dict)
    system = body["system"]
    assert isinstance(system, str)
    assert "Review the NDA from discloser." in system


@pytest.mark.integration
@respx.mock
async def test_skill_assembly_missing_required_input_returns_400(
    http_client: tuple[AsyncClient, BackendClient],
) -> None:
    """A skill with declared required inputs unbound → 400 + skill_input_missing."""

    client, _backend = http_client
    _mock_backend_skill(
        "alpha",
        body="Review {{document}}",
        inputs_yaml=("inputs:\n  required:\n    - name: document\n      type: document\n"),
    )

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "smart",
            "messages": [{"role": "user", "content": "hello"}],
            "lq_ai_skills": ["alpha"],
            # Required input "document" not provided.
        },
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "skill_input_missing"
    assert "alpha.document" in body["error"]["details"]["missing"]


@pytest.mark.integration
@respx.mock
async def test_skill_assembly_unknown_skill_returns_404(
    http_client: tuple[AsyncClient, BackendClient],
) -> None:
    """Unknown skill name → 404 with `skill_not_found`."""

    client, _backend = http_client
    respx.get(f"{BACKEND_URL}/api/v1/internal/skills/never-existed").mock(
        return_value=httpx.Response(
            404,
            json={
                "detail": {
                    "code": "not_found",
                    "message": "skill not found",
                    "details": {"skill_name": "never-existed"},
                }
            },
        )
    )

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "smart",
            "messages": [{"role": "user", "content": "hello"}],
            "lq_ai_skills": ["never-existed"],
        },
    )
    assert response.status_code == 404, response.text
    body = response.json()
    assert body["error"]["code"] == "skill_not_found"
    assert body["error"]["details"]["skill_name"] == "never-existed"


@pytest.mark.integration
@respx.mock
async def test_skill_assembly_backend_5xx_returns_502(
    http_client: tuple[AsyncClient, BackendClient],
) -> None:
    """Backend 5xx during skill fetch → 502 with `skill_fetch_failed`."""

    client, _backend = http_client
    respx.get(f"{BACKEND_URL}/api/v1/internal/skills/alpha").mock(
        return_value=httpx.Response(503, text="unavailable")
    )

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "smart",
            "messages": [{"role": "user", "content": "hello"}],
            "lq_ai_skills": ["alpha"],
        },
    )
    assert response.status_code == 502, response.text
    body = response.json()
    assert body["error"]["code"] == "skill_fetch_failed"


@pytest.mark.integration
@respx.mock
async def test_skill_assembly_caches_across_requests(
    http_client: tuple[AsyncClient, BackendClient],
) -> None:
    """Repeated requests with the same skill don't refetch within TTL."""

    client, backend = http_client
    skill_route = respx.get(f"{BACKEND_URL}/api/v1/internal/skills/alpha").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "alpha",
                "content_md": "Body",
                "content_yaml": "name: alpha\n",
            },
        )
    )
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg",
                "model": "claude-opus-4-7",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )
    )

    for _ in range(3):
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "smart",
                "messages": [{"role": "user", "content": "hi"}],
                "lq_ai_skills": ["alpha"],
            },
        )
        assert response.status_code == 200

    assert skill_route.call_count == 1
    assert await backend.cache.size() == 1


@pytest.mark.integration
@respx.mock
async def test_skill_assembly_multi_skill_concatenated_in_order(
    http_client: tuple[AsyncClient, BackendClient],
) -> None:
    """Two attached skills concatenate in the order the caller specified."""

    client, _backend = http_client
    _mock_backend_skill("alpha", body="Alpha body section")
    _mock_backend_skill("beta", body="Beta body section")
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg",
                "model": "claude-opus-4-7",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=_capture)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "smart",
            "messages": [{"role": "user", "content": "hi"}],
            "lq_ai_skills": ["alpha", "beta"],
        },
    )
    assert response.status_code == 200, response.text
    body = captured["body"]
    assert isinstance(body, dict)
    system = body["system"]
    assert isinstance(system, str)
    assert "Alpha body section" in system
    assert "Beta body section" in system
    assert system.index("Alpha body section") < system.index("Beta body section")

    response_body = response.json()
    assert response_body.get("lq_ai_applied_skills") == ["alpha", "beta"]


@pytest.mark.integration
@respx.mock
async def test_skill_name_audit_tag_set_from_first_skill(
    http_client: tuple[AsyncClient, BackendClient],
) -> None:
    """When `skill_name` is unset and `lq_ai_skills` is set, the gateway
    populates `skill_name` with the first attached skill (audit tagging).

    Verified indirectly by checking that the request still reaches
    Anthropic successfully and the response surfaces the applied set.
    """

    client, _backend = http_client
    _mock_backend_skill("alpha", body="A")
    _mock_backend_skill("beta", body="B")
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg",
                "model": "claude-opus-4-7",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )
    )

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "smart",
            "messages": [{"role": "user", "content": "hi"}],
            "lq_ai_skills": ["alpha", "beta"],
        },
    )
    assert response.status_code == 200
    # Audit log row should have skill_name = "alpha" — tested in
    # test_inference_b4 via the recorder; here we just verify the
    # response is healthy.
    assert response.json().get("lq_ai_applied_skills") == ["alpha", "beta"]


@pytest.mark.integration
@respx.mock
async def test_skill_assembly_no_skills_attached_is_unchanged(
    http_client: tuple[AsyncClient, BackendClient],
) -> None:
    """An ordinary chat with no `lq_ai_skills` is unchanged from B4 behavior."""

    client, _backend = http_client
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg",
                "model": "claude-opus-4-7",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=_capture)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "smart",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    # No skill applied → field is null/absent.
    assert body.get("lq_ai_applied_skills") in (None, [])
    # Anthropic body has no `system` field (B3 omits it when empty).
    sent = captured["body"]
    assert isinstance(sent, dict)
    assert sent.get("system") in (None, "", [])
