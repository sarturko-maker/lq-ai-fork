"""Wave D.2 — OpenAPI conformance for the new endpoints + fields.

These tests assert that the FastAPI-generated OpenAPI document reflects
the four Wave D.2 surfaces:

* ``GET /api/v1/skills/autocomplete`` (Task 2.5) is in the document.
* ``POST /api/v1/projects/sandbox/ensure`` (Task 2.2) is in the document.
* ``GET /api/v1/user-skills/{skill_id}/versions`` (Task 2.6) is in the
  document.
* The ``UserSkillCreate`` request schema (Task 2.4) carries
  ``slash_alias``, ``forked_from``, and ``source_message_id``.
* ``GET /api/v1/projects`` (Task 2.3) accepts ``include_sandbox`` and
  ``only_sandbox`` query parameters.

If the contract drifts (an endpoint is removed, a field is renamed, a
query parameter is dropped), these tests fail before any client code can
hit a 404 / unknown-field / 422 in CI.
"""

from __future__ import annotations

from app.main import app


def test_openapi_includes_new_endpoints() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/skills/autocomplete" in paths
    assert "/api/v1/projects/sandbox/ensure" in paths
    assert "/api/v1/user-skills/{skill_id}/versions" in paths


def test_user_skills_create_accepts_slash_alias() -> None:
    schema = app.openapi()
    body = schema["paths"]["/api/v1/user-skills"]["post"]["requestBody"]
    ref = body["content"]["application/json"]["schema"]["$ref"]
    cls = ref.rsplit("/", 1)[-1]
    props = schema["components"]["schemas"][cls]["properties"]
    assert "slash_alias" in props
    assert "forked_from" in props
    assert "source_message_id" in props


def test_projects_list_accepts_sandbox_filters() -> None:
    schema = app.openapi()
    params = schema["paths"]["/api/v1/projects"]["get"]["parameters"]
    names = {p["name"] for p in params}
    assert "include_sandbox" in names
    assert "only_sandbox" in names
