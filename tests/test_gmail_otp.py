"""Tests for Gmail IMAP OTP fetcher (mocked)."""

from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from seejob.integrations.gmail import (
    GmailImapConfig,
    GmailImapOtpFetcher,
    _extract_otp_from_message,
    _message_matches_domain,
    build_otp_fetcher,
    fetch_otp,
)


def _make_msg(subject: str, body: str, sender: str = "noreply@greenhouse.io") -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg.set_content(body)
    return msg


def test_extract_otp_from_message() -> None:
    msg = _make_msg("Your verification code", "Enter code 482910 to continue.")
    assert _extract_otp_from_message(msg) == "482910"


def test_message_matches_domain() -> None:
    msg = _make_msg("Your application update", "Use 1234 for boards.greenhouse.io")
    assert _message_matches_domain(msg, "boards.greenhouse.io") is True
    msg_other = _make_msg("Newsletter", "Weekly digest from our team")
    assert _message_matches_domain(msg_other, "other.com") is False


def test_gmail_imap_fetch_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    msg = _make_msg("OTP", "Your code is 556677 for lever.co login")
    raw = msg.as_bytes()

    mock_client = MagicMock()
    mock_client.search.return_value = (None, [b"1"])
    mock_client.fetch.return_value = (None, [(b"1", raw)])

    fetcher = GmailImapOtpFetcher(
        GmailImapConfig(host="imap.gmail.com", user="u@gmail.com", app_password="app")
    )

    with patch.object(fetcher, "_connect", return_value=mock_client):
        code = fetcher._fetch_latest("lever.co")

    assert code == "556677"
    mock_client.logout.assert_called_once()


def test_build_otp_fetcher_none_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEEJOB_GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_USER", raising=False)
    from seejob.core.config import get_settings

    get_settings.cache_clear()
    assert build_otp_fetcher() is None
    get_settings.cache_clear()


def test_fetch_otp_returns_none_without_config() -> None:
    with patch("seejob.integrations.gmail.build_otp_fetcher", return_value=None):
        assert fetch_otp("example.com", timeout=0.1) is None


def test_fetch_otp_delegates_to_fetcher() -> None:
    mock_fetcher = MagicMock()
    mock_fetcher.fetch_otp.return_value = "112233"
    with patch("seejob.integrations.gmail.build_otp_fetcher", return_value=mock_fetcher):
        assert fetch_otp("example.com", timeout=5) == "112233"
