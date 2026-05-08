"""Pytest configuration for the cross-subsystem `tests/` directory.

Per CLAUDE.md, ``api/`` and ``gateway/`` are self-contained services that
talk over HTTP. The cross-subsystem tests in this directory are a tiny
exception — they exist exclusively to verify *contracts* that span both
sides (e.g., the error-code enum stays in sync). They import from both
``api.app`` and ``gateway.app`` via filesystem path injection rather
than via a shared package.

Each test imports the modules it needs by hand (with explicit ``sys.path``
manipulation) so a missing subsystem fails loudly rather than masking the
contract violation.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Make both subsystems importable as top-level ``app.*`` packages, but
# NOT at the same time. Each test imports one or the other by adjusting
# sys.path before the import. The test_error_code_contract test loads
# both via importlib + reload to avoid the collision.

API_DIR = ROOT / "api"
GATEWAY_DIR = ROOT / "gateway"


def ensure_paths_on_syspath() -> None:
    """Add api/ and gateway/ to sys.path if not already present.

    Used by tests in this dir; idempotent.
    """

    for p in (API_DIR, GATEWAY_DIR):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)


ensure_paths_on_syspath()
