"""WOPI host schemas + the pure lock state machine (libreoffice-editor Slice 2/3, ADR-F047).

Pieces, all model-call-free:

* ``CheckFileInfoResponse`` — the WOPI ``CheckFileInfo`` body. Field names are the
  WOPI property names verbatim (PascalCase) so the JSON is the wire contract;
  ``None`` fields are excluded (WOPI: omit a property to take its default, never
  send ``null``). Slice 3 makes the session **editable** — ``UserCanWrite=true`` /
  ``SupportsUpdate=true`` / ``ReadOnly=false`` — so the lawyer's edits save back
  through PutFile (the read-only Slice-2 viewer is now read-write).
* ``decide_lock`` — the pure WOPI lock state machine (LOCK / GET_LOCK /
  REFRESH_LOCK / UNLOCK / UNLOCK_AND_RELOCK). Takes the *effective* current lock
  (``None`` if absent or expired) + the request headers, returns a ``LockOutcome``
  describing the HTTP status, what to persist, and the ``X-WOPI-Lock`` echo. The
  WOPI handler wires the DB read/write around it; all the protocol semantics
  (409 + current-lock echo on mismatch, empty-string echo when unlocked, 200
  refresh on a matching lock) are testable here without a DB.
* ``EditorSessionResponse`` — what the mint endpoint returns to the cockpit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Lock constants
# ---------------------------------------------------------------------------

# WOPI lock timeout. A lock not refreshed within this window is treated as
# absent (the protocol's documented 30-minute default). Collabora refreshes
# locks well inside it.
LOCK_TTL_SECONDS = 1800

# The X-WOPI-Override values the lock state machine handles. PUT (PutFile) and
# the *-RELATIVE / RENAME_FILE overrides are NOT here — the handler answers 501
# to those this slice (PutFile is Slice 3; PutRelativeFile is disabled via
# UserCanNotWriteRelative). UNLOCK_AND_RELOCK is dispatched as override=LOCK with
# an X-WOPI-OldLock header present, so it is not a distinct override string.
LOCK_OVERRIDES = frozenset({"LOCK", "GET_LOCK", "REFRESH_LOCK", "UNLOCK"})


# ---------------------------------------------------------------------------
# CheckFileInfo
# ---------------------------------------------------------------------------


class CheckFileInfoResponse(BaseModel):
    """WOPI ``CheckFileInfo`` response (editable edit session, Slice 3).

    PascalCase field names are the WOPI wire property names. Serialize with
    ``model_dump(exclude_none=True)`` / FastAPI's ``response_model_exclude_none``
    so optional properties left ``None`` are omitted rather than sent as null.
    """

    model_config = ConfigDict(extra="forbid")

    # Required by WOPI for the editor to open the document at all.
    BaseFileName: str = Field(description="Bare filename incl. extension, NO path.")
    OwnerId: str = Field(description="Stable owner id, alphanumeric (uuid hex).")
    Size: int = Field(description="File size in bytes.")
    UserId: str = Field(description="Stable current-user id, alphanumeric (uuid hex).")
    Version: str = Field(description="Opaque version string; changes on content change.")

    # Session capabilities. Slice 3 = editable (PutFile save-back enabled).
    # PutRelativeFile/RenameFile stay disabled (UserCanNotWriteRelative) — the
    # save-back is in-place to the same WOPI id (ADR-F047 Slice-3 snapshot model).
    UserCanWrite: bool = True
    ReadOnly: bool = False
    SupportsUpdate: bool = True
    UserCanNotWriteRelative: bool = True
    SupportsLocks: bool = True
    SupportsGetLock: bool = True
    SupportsExtendedLockLength: bool = True

    # Display / integration.
    UserFriendlyName: str = Field(description="Shown in the editor; becomes w:author on edits.")
    LastModifiedTime: str = Field(description="ISO 8601 last-modified time.")
    PostMessageOrigin: str | None = Field(
        default=None,
        description="Browser origin Collabora may postMessage to (Slice-4 reskin).",
    )


# ---------------------------------------------------------------------------
# Lock state machine (pure)
# ---------------------------------------------------------------------------


class LockAction(StrEnum):
    """What the WOPI handler must persist after a lock decision."""

    NONE = "none"
    """Persist nothing (GET_LOCK, every conflict/400)."""
    SET = "set"
    """Upsert the lock to ``lock_to_persist`` with a fresh TTL."""
    CLEAR = "clear"
    """Delete the lock row (a successful UNLOCK)."""


@dataclass(frozen=True)
class LockOutcome:
    """The decision for one lock-family request.

    Attributes:
        status: HTTP status to return (200 / 400 / 409).
        action: What to persist (:class:`LockAction`).
        lock_to_persist: The lock value to store when ``action == SET``.
        response_lock: Value for the ``X-WOPI-Lock`` response header. ``None`` =>
            omit the header (200 success on LOCK/REFRESH/UNLOCK, and 400). A
            string (possibly empty) => set it (GET_LOCK always; every 409 echoes
            the current lock, the empty string when the file is unlocked).
        failure_reason: Surfaced as the ``X-WOPI-LockFailureReason`` response
            header — an advisory, free-form diagnostic string (the WOPI client
            treats it as informational/logging, never as control flow).
    """

    status: int
    action: LockAction
    lock_to_persist: str | None = None
    response_lock: str | None = None
    failure_reason: str | None = None


def _conflict(current_lock: str | None, reason: str) -> LockOutcome:
    """A 409 that echoes the current lock (empty string when unlocked)."""
    return LockOutcome(
        status=409,
        action=LockAction.NONE,
        response_lock=current_lock if current_lock is not None else "",
        failure_reason=reason,
    )


def decide_lock(
    override: str,
    *,
    x_wopi_lock: str | None,
    x_wopi_oldlock: str | None,
    current_lock: str | None,
) -> LockOutcome:
    """Pure WOPI lock state machine.

    Args:
        override: The (already upper-cased) ``X-WOPI-Override`` value; must be one
            of :data:`LOCK_OVERRIDES`.
        x_wopi_lock: The ``X-WOPI-Lock`` request header (the lock id), or ``None``.
        x_wopi_oldlock: The ``X-WOPI-OldLock`` request header. Its presence turns
            an override of ``LOCK`` into ``UNLOCK_AND_RELOCK``.
        current_lock: The file's effective current lock — ``None`` if there is no
            lock or it has expired (the caller resolves expiry before calling).

    Returns:
        A :class:`LockOutcome`. ``override`` outside :data:`LOCK_OVERRIDES` raises
        ``ValueError`` (the handler filters first and 501s the rest).
    """
    if override not in LOCK_OVERRIDES:
        raise ValueError(f"decide_lock called with non-lock override {override!r}")

    if override == "GET_LOCK":
        # Never creates a lock; always 200 with the current lock (empty if none).
        return LockOutcome(
            status=200,
            action=LockAction.NONE,
            response_lock=current_lock if current_lock is not None else "",
        )

    if override == "LOCK" and x_wopi_oldlock is not None:
        # UNLOCK_AND_RELOCK: atomically replace old lock with the new one.
        if not x_wopi_lock:
            return LockOutcome(status=400, action=LockAction.NONE)
        if current_lock is not None and current_lock == x_wopi_oldlock:
            return LockOutcome(status=200, action=LockAction.SET, lock_to_persist=x_wopi_lock)
        return _conflict(current_lock, "old lock mismatch")

    if override == "LOCK":
        if not x_wopi_lock:
            return LockOutcome(status=400, action=LockAction.NONE)
        if current_lock is None:
            return LockOutcome(status=200, action=LockAction.SET, lock_to_persist=x_wopi_lock)
        if current_lock == x_wopi_lock:
            # Same lock => treat as a refresh (re-set with a fresh TTL).
            return LockOutcome(status=200, action=LockAction.SET, lock_to_persist=x_wopi_lock)
        return _conflict(current_lock, "already locked")

    if override == "REFRESH_LOCK":
        if not x_wopi_lock:
            return LockOutcome(status=400, action=LockAction.NONE)
        if current_lock is not None and current_lock == x_wopi_lock:
            return LockOutcome(status=200, action=LockAction.SET, lock_to_persist=current_lock)
        return _conflict(current_lock, "lock mismatch or not locked")

    # override == "UNLOCK"
    if not x_wopi_lock:
        return LockOutcome(status=400, action=LockAction.NONE)
    if current_lock is not None and current_lock == x_wopi_lock:
        return LockOutcome(status=200, action=LockAction.CLEAR)
    return _conflict(current_lock, "lock mismatch or not locked")


def decide_putfile_lock(*, x_wopi_lock: str | None, current_lock: str | None) -> LockOutcome:
    """Pure WOPI PutFile lock precondition (no lock mutation, just allow/deny).

    PutFile never changes the lock — it only checks whether the caller may write:

    * **Unlocked** (``current_lock is None``) → proceed (200). WOPI permits a
      PutFile on an unlocked file; Collabora locks before editing in practice, so
      this also tolerates a lock that expired mid-session rather than 409-ing a
      legitimate save.
    * **Locked, header matches** → proceed (200).
    * **Locked, header missing/mismatched** → 409 echoing the current lock (the
      same shape the lock family uses), so the editor surfaces the conflict.

    Returns a :class:`LockOutcome` with ``action == NONE`` always (the lock row is
    untouched); only ``status`` / ``response_lock`` matter to the caller.
    """
    if current_lock is None or current_lock == x_wopi_lock:
        return LockOutcome(status=200, action=LockAction.NONE)
    return _conflict(current_lock, "lock mismatch on PutFile")


# ---------------------------------------------------------------------------
# Editor-session mint
# ---------------------------------------------------------------------------


class EditorSessionResponse(BaseModel):
    """What ``POST /files/{file_id}/editor-session`` returns to the cockpit.

    The cockpit (Slice 4) combines these with Collabora's discovery ``urlsrc`` to
    launch the editor iframe. ``access_token_ttl`` is **epoch milliseconds** (the
    WOPI convention), not a duration. ``wopi_src`` is the absolute CheckFileInfo
    URL the Collabora *server* calls back — the in-network ``api`` origin, with no
    trailing slash and no token.
    """

    access_token: str = Field(description="The WOPI access token (a signed editor-session JWT).")
    access_token_ttl: int = Field(
        description="Absolute token expiry as epoch milliseconds (WOPI access_token_ttl)."
    )
    wopi_src: str = Field(
        description="Absolute CheckFileInfo URL Collabora calls back (the WOPISrc base)."
    )
