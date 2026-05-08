"""ORM models for the LQ.AI backend.

Each model corresponds to a table in docs/db-schema.md. The migration in
api/alembic/versions/ is the authoritative DDL — these models reflect what
the migration produces and are the read/write surface for application code.

Import side-effect: importing this module registers every model with the
declarative base, so Alembic's autogenerate (when used) sees them.
"""

from __future__ import annotations

from app.models.audit import AuditLog
from app.models.file import File
from app.models.inference import InferenceRoutingLog
from app.models.project import Project, ProjectFile, ProjectSkill
from app.models.user import User, UserSession

__all__ = [
    "AuditLog",
    "File",
    "InferenceRoutingLog",
    "Project",
    "ProjectFile",
    "ProjectSkill",
    "User",
    "UserSession",
]
