"""P0-06: credential redaction in structured logging (tests first)."""

from __future__ import annotations

import logging

import pytest
from vhecfsck.logging import (
    RedactionFilter,
    configure_logging,
    redact_secrets,
)


@pytest.mark.parametrize(
    ("secret", "must_not_survive"),
    [
        ("postgres://alice:s3cret@db.example:5432/app", "s3cret"),
        ("postgresql://bob:p%40ss@localhost/vectors", "p%40ss"),
        ("https://api.example/v1?api_key=sk-live-abc123", "sk-live-abc123"),
        (
            "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
            "eyJhbGciOiJIUzI1NiJ9.payload.sig",
        ),
        ("authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        (
            "token=ghp_abcdefghijklmnopqrstuvwxyz0123456789",
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        ),
        (
            "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        ),
        ("api_key=AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
        ("postgres://u:pass+word@host/db", "pass+word"),
        ("postgres://u:p@ss(word)[1].*?@host/db", "p@ss(word)[1].*?"),
        ("mysql://root:hunter2@127.0.0.1:3306/x", "hunter2"),
        ("https://x?token=super-secret-value-here", "super-secret-value-here"),
    ],
)
def test_redact_secrets_removes_credentials(
    secret: str,
    must_not_survive: str,
) -> None:
    redacted = redact_secrets(secret)
    assert must_not_survive not in redacted
    assert "REDACTED" in redacted


def test_password_with_regex_metacharacters_is_redacted() -> None:
    raw = "postgres://u:p@ss(word)[1].*?@host/db"
    out = redact_secrets(raw)
    assert "p@ss(word)[1].*?" not in out
    assert "REDACTED" in out


def test_non_secret_file_url_survives() -> None:
    url = "file:///data/x.lance"
    assert redact_secrets(url) == url


def test_redaction_filter_on_log_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MY_API_KEY", "env-secret-value-xyz")
    record = logging.LogRecord(
        name="vhecfsck.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="connect %s key=%s",
        args=("postgres://u:pw@h/db", "env-secret-value-xyz"),
        exc_info=None,
    )
    assert RedactionFilter().filter(record) is True
    rendered = record.getMessage()
    assert "pw" not in rendered
    assert "env-secret-value-xyz" not in rendered
    assert "REDACTED" in rendered


def test_configure_logging_writes_to_stderr_not_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(verbosity=1, log_format="human")
    logging.getLogger("vhecfsck").warning("hello-diagnostic")
    captured = capsys.readouterr()
    assert "hello-diagnostic" in captured.err
    assert captured.out == ""


def test_no_flag_disables_redaction() -> None:
    assert not hasattr(RedactionFilter, "disabled")
    doc = (RedactionFilter.__doc__ or "").lower()
    assert "no disable" in doc or "no flag" in doc or "always" in doc
