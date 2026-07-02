"""Unit tests for the uvicorn access-log secret scrubber (SAAS-2, ADR-F059).

The WOPI editor-session token rides as an `access_token` query param and would
otherwise land in the default uvicorn access log in every environment.
"""

from __future__ import annotations

import logging

import pytest

from app.observability import AccessTokenLogScrubFilter


def _uvicorn_access_record(full_path: str) -> logging.LogRecord:
    """A record shaped like uvicorn's access log line."""
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("203.0.113.5:44210", "GET", full_path, "1.1", 200),
        exc_info=None,
    )


@pytest.mark.unit
def test_redacts_access_token_in_request_line() -> None:
    f = AccessTokenLogScrubFilter()
    record = _uvicorn_access_record("/api/v1/wopi/files/abcd?access_token=SUPERSECRETVALUE123&x=1")
    assert f.filter(record) is True
    rendered = record.getMessage()
    assert "SUPERSECRETVALUE123" not in rendered
    assert "access_token=REDACTED" in rendered
    # Non-secret query params survive.
    assert "x=1" in rendered


@pytest.mark.unit
def test_leaves_unrelated_records_untouched() -> None:
    f = AccessTokenLogScrubFilter()
    record = _uvicorn_access_record("/api/v1/chats/123?page=2")
    assert f.filter(record) is True
    assert record.getMessage() == '203.0.113.5:44210 - "GET /api/v1/chats/123?page=2 HTTP/1.1" 200'


@pytest.mark.unit
def test_redacts_when_token_is_in_preformatted_message() -> None:
    f = AccessTokenLogScrubFilter()
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="GET /api/v1/wopi/files/x?access_token=TOKENabc served",
        args=(),
        exc_info=None,
    )
    assert f.filter(record) is True
    assert "TOKENabc" not in record.getMessage()
    assert "access_token=REDACTED" in record.getMessage()


@pytest.mark.unit
@pytest.mark.parametrize("bad_args", [12345, {"key": "value"}, None])
def test_malformed_record_does_not_raise(bad_args: object) -> None:
    f = AccessTokenLogScrubFilter()
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="opaque line with no token",
        args=(),
        exc_info=None,
    )
    # Simulate a record whose args got set to an unexpected shape after
    # construction — the filter must never raise on it.
    record.args = bad_args  # type: ignore[assignment]
    assert f.filter(record) is True
