"""Gmail OTP fetcher — IMAP implementation with MCP-ready interface."""

from __future__ import annotations

import email
import imaplib
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.header import decode_header
from typing import Protocol

from seejob.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

OTP_PATTERN = re.compile(r"\b(\d{4,8})\b")
OTP_SUBJECT_HINTS = ("verification", "otp", "one-time", "security code", "login code", "confirm")


class OtpFetcher(Protocol):
    """Protocol for OTP retrieval — IMAP today, Gmail API / MCP tomorrow."""

    def fetch_otp(self, domain: str, *, timeout: float = 60.0) -> str | None:
        """Return the latest OTP code for *domain*, or None on timeout."""


@dataclass
class GmailImapConfig:
    """IMAP connection settings for Gmail app-password access."""

    host: str
    user: str
    app_password: str


class BaseOtpProvider(ABC):
    """Abstract OTP provider with polling loop."""

    @abstractmethod
    def _fetch_latest(self, domain: str) -> str | None:
        """Single poll attempt — return OTP if found."""

    def fetch_otp(self, domain: str, *, timeout: float = 60.0) -> str | None:
        """Poll inbox until an OTP arrives or *timeout* elapses."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            code = self._fetch_latest(domain)
            if code:
                return code
            time.sleep(3)
        return None


class GmailImapOtpFetcher(BaseOtpProvider):
    """Fetch OTP codes from Gmail via IMAP."""

    def __init__(self, config: GmailImapConfig) -> None:
        self._config = config

    def _connect(self) -> imaplib.IMAP4_SSL:
        client = imaplib.IMAP4_SSL(self._config.host)
        client.login(self._config.user, self._config.app_password)
        client.select("INBOX")
        return client

    def _fetch_latest(self, domain: str) -> str | None:
        try:
            client = self._connect()
        except imaplib.IMAP4.error as exc:
            logger.warning("Gmail IMAP login failed: %s", exc)
            return None

        try:
            _, data = client.search(None, "UNSEEN")
            ids = data[0].split() if data and data[0] else []
            if not ids:
                _, data = client.search(None, "ALL")
                ids = (data[0].split()[-5:] if data and data[0] else [])

            for msg_id in reversed(ids):
                _, msg_data = client.fetch(msg_id, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                if not isinstance(raw, bytes):
                    continue
                msg = email.message_from_bytes(raw)
                if not _message_matches_domain(msg, domain):
                    continue
                code = _extract_otp_from_message(msg)
                if code:
                    return code
        except imaplib.IMAP4.error as exc:
            logger.warning("Gmail IMAP fetch failed: %s", exc)
        finally:
            try:
                client.logout()
            except imaplib.IMAP4.error:
                pass
        return None


class GmailApiOtpFetcher(BaseOtpProvider):
    """Stub for Gmail API / MCP integration — raises NotImplementedError on use."""

    def _fetch_latest(self, domain: str) -> str | None:
        raise NotImplementedError(
            "Gmail API OTP fetcher is a stub. Use GmailImapOtpFetcher or wire MCP."
        )


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _message_matches_domain(msg: email.message.Message, domain: str) -> bool:
    subject = _decode_header_value(msg.get("Subject")).lower()
    sender = _decode_header_value(msg.get("From")).lower()
    body = _get_message_body(msg).lower()
    domain_l = domain.lower()
    if domain_l in subject or domain_l in sender or domain_l in body:
        return True
    return any(hint in subject for hint in OTP_SUBJECT_HINTS)


def _get_message_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        chunks: list[str] = []
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    chunks.append(payload.decode("utf-8", errors="replace"))
        return "\n".join(chunks)
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return str(payload or "")


def _extract_otp_from_message(msg: email.message.Message) -> str | None:
    subject = _decode_header_value(msg.get("Subject"))
    body = _get_message_body(msg)
    for text in (subject, body):
        match = OTP_PATTERN.search(text)
        if match:
            return match.group(1)
    return None


def build_otp_fetcher(settings: Settings | None = None) -> OtpFetcher | None:
    """Return an IMAP OTP fetcher when Gmail credentials are configured."""
    cfg = settings or get_settings()
    if not cfg.gmail_user or not cfg.gmail_app_password:
        return None
    return GmailImapOtpFetcher(
        GmailImapConfig(
            host=cfg.gmail_imap_host,
            user=cfg.gmail_user,
            app_password=cfg.gmail_app_password,
        )
    )


def fetch_otp(domain: str, *, timeout: float = 60.0, settings: Settings | None = None) -> str | None:
    """Convenience wrapper — fetch OTP via configured provider."""
    fetcher = build_otp_fetcher(settings)
    if fetcher is None:
        logger.debug("No Gmail OTP fetcher configured for domain %s", domain)
        return None
    return fetcher.fetch_otp(domain, timeout=timeout)
