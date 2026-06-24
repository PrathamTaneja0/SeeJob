"""Site credential lookup, session persistence, and login flow hooks."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from seejob.core.security import EncryptionError, decrypt_value, encrypt_value
from seejob.integrations.gmail import OtpFetcher, build_otp_fetcher, fetch_otp
from seejob.models.site_account import SiteAccount

logger = logging.getLogger(__name__)

# In-memory manual OTP queue keyed by application_id (dashboard injection).
_pending_otps: dict[int, str] = {}

LOGIN_USERNAME_SELECTORS = [
    'input[type="email"]',
    'input[name*="email" i]',
    'input[name*="user" i]',
    'input[id*="email" i]',
    'input[id*="user" i]',
]
LOGIN_PASSWORD_SELECTORS = ['input[type="password"]']
LOGIN_SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Sign in")',
    'button:has-text("Log in")',
    'button:has-text("Continue")',
]
OTP_SELECTORS = [
    'input[name*="otp" i]',
    'input[name*="code" i]',
    'input[id*="otp" i]',
    'input[id*="code" i]',
    'input[autocomplete="one-time-code"]',
    'input[inputmode="numeric"]',
]


@dataclass
class SiteCredentials:
    """Decrypted credentials for a domain."""

    account_id: int
    platform: str
    domain: str | None
    username: str
    password: str | None


def mask_secret(value: str | None, visible: int = 0) -> str:
    """Mask a secret for API responses."""
    if not value:
        return "****"
    if visible > 0 and len(value) > visible:
        return value[:visible] + "****"
    return "****"


def get_site_account(db: Session, person_id: int, domain: str) -> SiteAccount | None:
    """Find active site account matching person and domain."""
    domain_l = domain.lower()
    accounts = db.scalars(
        select(SiteAccount).where(
            SiteAccount.person_id == person_id,
            SiteAccount.is_active.is_(True),
        )
    ).all()
    for account in accounts:
        if account.domain and account.domain.lower() == domain_l:
            return account
        if account.platform.lower() in domain_l or domain_l in account.platform.lower():
            return account
    return None


def get_credentials(db: Session, person_id: int, domain: str) -> SiteCredentials | None:
    """Decrypt and return credentials for a domain."""
    account = get_site_account(db, person_id, domain)
    if account is None:
        return None
    try:
        username = decrypt_value(account.username_encrypted)
        password = (
            decrypt_value(account.password_encrypted) if account.password_encrypted else None
        )
    except EncryptionError:
        logger.warning("Failed to decrypt credentials for site account %s", account.id)
        return None
    return SiteCredentials(
        account_id=account.id,
        platform=account.platform,
        domain=account.domain,
        username=username,
        password=password,
    )


def load_session_cookies(db: Session, person_id: int, domain: str) -> list[dict[str, Any]] | None:
    """Load encrypted session cookies from SiteAccount."""
    account = get_site_account(db, person_id, domain)
    if account is None or not account.session_data_encrypted:
        return None
    try:
        plaintext = decrypt_value(account.session_data_encrypted)
        data = json.loads(plaintext)
        if isinstance(data, list):
            return data
    except (EncryptionError, json.JSONDecodeError) as exc:
        logger.debug("Could not load session for %s: %s", domain, exc)
    return None


def save_session_cookies(
    db: Session,
    person_id: int,
    domain: str,
    cookies: list[dict[str, Any]],
) -> None:
    """Encrypt and persist session cookies to SiteAccount."""
    account = get_site_account(db, person_id, domain)
    if account is None:
        logger.debug("No site account to save session for domain %s", domain)
        return
    try:
        account.session_data_encrypted = encrypt_value(json.dumps(cookies))
        account.last_login_at = datetime.now(UTC).isoformat()
        db.commit()
    except EncryptionError as exc:
        logger.warning("Failed to encrypt session for %s: %s", domain, exc)


def store_manual_otp(application_id: int, otp: str) -> None:
    """Store OTP injected from dashboard for pending login."""
    cleaned = re.sub(r"\s+", "", otp.strip())
    _pending_otps[application_id] = cleaned


def pop_manual_otp(application_id: int) -> str | None:
    """Retrieve and clear a manually injected OTP."""
    return _pending_otps.pop(application_id, None)


def peek_manual_otp(application_id: int) -> str | None:
    """Peek at manual OTP without removing."""
    return _pending_otps.get(application_id)


def resolve_otp(
    domain: str,
    *,
    application_id: int | None = None,
    timeout: float = 60.0,
    fetcher: OtpFetcher | None = None,
) -> str | None:
    """Resolve OTP from manual injection first, then Gmail IMAP."""
    if application_id is not None:
        manual = peek_manual_otp(application_id)
        if manual:
            pop_manual_otp(application_id)
            return manual
    provider = fetcher or build_otp_fetcher()
    if provider is None:
        return fetch_otp(domain, timeout=timeout) if fetcher is None else None
    return provider.fetch_otp(domain, timeout=timeout)


async def try_login(
    page: Any,
    credentials: SiteCredentials,
    *,
    domain: str,
    application_id: int | None = None,
    otp_fetcher: OtpFetcher | None = None,
    otp_timeout: float = 60.0,
) -> bool:
    """Attempt automated login on a Playwright page. Returns True on success."""
    try:
        for selector in LOGIN_USERNAME_SELECTORS:
            el = await page.query_selector(selector)
            if el:
                await el.fill(credentials.username)
                break

        for selector in LOGIN_PASSWORD_SELECTORS:
            el = await page.query_selector(selector)
            if el and credentials.password:
                await el.fill(credentials.password)
                break

        for selector in LOGIN_SUBMIT_SELECTORS:
            el = await page.query_selector(selector)
            if el:
                await el.click()
                break

        await page.wait_for_timeout(2000)

        otp_field = await _find_otp_field(page)
        if otp_field:
            code = resolve_otp(
                domain,
                application_id=application_id,
                timeout=otp_timeout,
                fetcher=otp_fetcher,
            )
            if not code:
                return False
            await otp_field.fill(code)
            for selector in LOGIN_SUBMIT_SELECTORS:
                el = await page.query_selector(selector)
                if el:
                    await el.click()
                    break
            await page.wait_for_timeout(2000)

        for selector in LOGIN_PASSWORD_SELECTORS:
            if await page.query_selector(selector):
                return False
        return True
    except Exception as exc:
        logger.warning("Login attempt failed for %s: %s", domain, exc)
        return False


async def _find_otp_field(page: Any) -> Any | None:
    for selector in OTP_SELECTORS:
        el = await page.query_selector(selector)
        if el:
            return el
    return None
