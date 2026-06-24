"""Site account CRUD with Fernet encryption."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seejob.core.security import EncryptionError, encrypt_value
from seejob.models.site_account import SiteAccount
from seejob.schemas.site_account import SiteAccountCreate, SiteAccountRead, SiteAccountUpdate
from seejob.services.auth import mask_secret


class SiteAccountError(ValueError):
    """Raised when site account operations fail."""


def _to_read(account: SiteAccount, *, username: str) -> SiteAccountRead:
    return SiteAccountRead(
        id=account.id,
        person_id=account.person_id,
        platform=account.platform,
        domain=account.domain,
        username=username,
        password_masked=mask_secret(account.password_encrypted and "set"),
        has_session=bool(account.session_data_encrypted),
        is_active=account.is_active,
        last_login_at=account.last_login_at,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def list_site_accounts(
    db: Session,
    *,
    person_id: int | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[SiteAccountRead]:
    """List site accounts with masked passwords."""
    stmt = select(SiteAccount).order_by(SiteAccount.id.desc()).offset(skip).limit(limit)
    if person_id is not None:
        stmt = stmt.where(SiteAccount.person_id == person_id)
    accounts = db.scalars(stmt).all()
    result: list[SiteAccountRead] = []
    for account in accounts:
        from seejob.core.security import decrypt_value

        try:
            username = decrypt_value(account.username_encrypted)
        except EncryptionError:
            username = "(encrypted)"
        result.append(_to_read(account, username=username))
    return result


def get_site_account_by_id(db: Session, account_id: int) -> SiteAccountRead:
    """Get a single site account."""
    account = db.get(SiteAccount, account_id)
    if account is None:
        raise SiteAccountError(f"Site account {account_id} not found")
    from seejob.core.security import decrypt_value

    try:
        username = decrypt_value(account.username_encrypted)
    except EncryptionError:
        username = "(encrypted)"
    return _to_read(account, username=username)


def create_site_account(db: Session, data: SiteAccountCreate) -> SiteAccountRead:
    """Create site account with encrypted credentials."""
    try:
        username_enc = encrypt_value(data.username)
        password_enc = encrypt_value(data.password) if data.password else None
    except EncryptionError as exc:
        raise SiteAccountError(str(exc)) from exc

    account = SiteAccount(
        person_id=data.person_id,
        platform=data.platform,
        domain=data.domain,
        username_encrypted=username_enc,
        password_encrypted=password_enc,
        is_active=data.is_active,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return _to_read(account, username=data.username)


def update_site_account(
    db: Session, account_id: int, data: SiteAccountUpdate
) -> SiteAccountRead:
    """Update site account fields."""
    account = db.get(SiteAccount, account_id)
    if account is None:
        raise SiteAccountError(f"Site account {account_id} not found")

    if data.platform is not None:
        account.platform = data.platform
    if data.domain is not None:
        account.domain = data.domain
    if data.is_active is not None:
        account.is_active = data.is_active
    if data.username is not None:
        try:
            account.username_encrypted = encrypt_value(data.username)
        except EncryptionError as exc:
            raise SiteAccountError(str(exc)) from exc
    if data.password is not None:
        try:
            account.password_encrypted = encrypt_value(data.password)
        except EncryptionError as exc:
            raise SiteAccountError(str(exc)) from exc

    db.commit()
    db.refresh(account)
    from seejob.core.security import decrypt_value

    username = decrypt_value(account.username_encrypted)
    return _to_read(account, username=username)


def delete_site_account(db: Session, account_id: int) -> None:
    """Delete a site account."""
    account = db.get(SiteAccount, account_id)
    if account is None:
        raise SiteAccountError(f"Site account {account_id} not found")
    db.delete(account)
    db.commit()
