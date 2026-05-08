"""Skill prompt-assembly package (C2).

The gateway's :mod:`app.api.inference` handler imports
:func:`assemble_skill_prompt` from here. The package keeps the
pure-Python prompt assembly logic separate from the HTTP client
(:mod:`app.clients.backend`) so unit tests can exercise the assembler
without touching the wire.
"""

from app.skills.assembler import (
    SKILL_INPUT_VARIABLE_RE,
    assemble_skill_prompt,
    extract_required_inputs,
    interpolate,
)

__all__ = [
    "SKILL_INPUT_VARIABLE_RE",
    "assemble_skill_prompt",
    "extract_required_inputs",
    "interpolate",
]
