"""Drift guard: mail-bridge bounds must equal the api's envelope bounds (INTAKE-2).

The mail-bridge is a separate service with a separate image, so it cannot import
``app.schemas.intake``; it RESTATES the same caps in
``mail-bridge/app/normalize.py``. That duplication is deliberate — and it is
exactly the kind that rots silently:

* a bridge bound LOOSER than the api's turns every oversize arrival into a 422,
  and since AgentMail keeps no replayable delivery log
  (``docs/fork/evidence/intake-probe/findings.md``), that email is simply LOST;
* a bridge bound TIGHTER silently truncates content the api would have accepted.

Neither shows up in either service's own tests. This guard reads the bridge's
constants out of the file (no cross-service import, no new dependency) and
asserts equality with the api's.

SKIPPED when mail-bridge/ is absent — a containerized api test run may not mount
it. CI's full checkout enforces it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.schemas import intake

_BRIDGE_NORMALIZE = Path(__file__).resolve().parents[2] / "mail-bridge" / "app" / "normalize.py"

pytestmark = pytest.mark.skipif(
    not _BRIDGE_NORMALIZE.is_file(),
    reason="mail-bridge/app/normalize.py not present in this checkout (drift guard skipped)",
)

# bridge constant name -> the api value it must equal
_PAIRS = {
    "MAX_ATTACHMENTS": intake.MAX_ATTACHMENTS,
    "MAX_ATTACHMENT_BYTES": intake.MAX_ATTACHMENT_DECODED_BYTES,
    "MAX_AGGREGATE_ATTACHMENT_BYTES": intake.MAX_AGGREGATE_ATTACHMENT_DECODED_BYTES,
    "MAX_BODY_TEXT_CHARS": intake.MAX_BODY_TEXT_CHARS,
    "MAX_ADDR_CHARS": intake._ADDR_MAX_CHARS,
    # INTAKE-4a (ADR-F088): the two header caps. ``References`` has its own,
    # larger one because it grows without bound and the layer-2 resolver reads it.
    "MAX_HEADER_VALUE_CHARS": intake._HEADER_VALUE_MAX_CHARS,
    "MAX_REFERENCES_VALUE_CHARS": intake._REFERENCES_VALUE_MAX_CHARS,
}


def _bridge_constants() -> dict[str, int]:
    """Module-level ``NAME = <int expression>`` assignments, evaluated safely.

    ``ast.literal_eval`` alone cannot fold ``25 * 1024 * 1024``, so the value is
    compiled and evaluated with no builtins and no names in scope — the file is
    parsed, never imported.
    """

    tree = ast.parse(_BRIDGE_NORMALIZE.read_text(encoding="utf-8"))
    found: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in _PAIRS:
            continue
        # Literal arithmetic only: no builtins, no names, file parsed not imported.
        value = eval(
            compile(ast.Expression(body=node.value), "<bounds>", "eval"), {"__builtins__": {}}, {}
        )
        assert isinstance(value, int)
        found[target.id] = value
    return found


@pytest.mark.unit
def test_every_bound_is_restated_by_the_bridge() -> None:
    missing = set(_PAIRS) - set(_bridge_constants())
    assert not missing, f"mail-bridge stopped declaring: {sorted(missing)}"


@pytest.mark.unit
@pytest.mark.parametrize("name", sorted(_PAIRS))
def test_bridge_bound_matches_the_api(name: str) -> None:
    bridge = _bridge_constants()[name]
    assert bridge == _PAIRS[name], (
        f"mail-bridge {name}={bridge} but the api enforces {_PAIRS[name]}. "
        "A looser bridge bound loses email to a 422 that cannot be replayed; "
        "a tighter one silently truncates. Change both together."
    )


@pytest.mark.unit
def test_bridge_forwards_exactly_the_headers_the_api_allowlists() -> None:
    """The bridge sends only what ``ALLOWED_HEADER_KEYS`` admits."""

    text = _BRIDGE_NORMALIZE.read_text(encoding="utf-8")
    for key in intake.ALLOWED_HEADER_KEYS:
        assert f'"{key}"' in text, f"mail-bridge no longer forwards the {key} header"
