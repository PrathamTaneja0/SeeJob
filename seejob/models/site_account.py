"""Encrypted site account credentials."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seejob.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seejob.models.person import Person


class SiteAccount(Base, TimestampMixin):
    """Per-platform account with Fernet-encrypted credentials.

    username_encrypted and password_encrypted store ciphertext only.
    Session cookies for ATS persistence are stored separately as encrypted JSON.
    """

    __tablename__ = "site_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(255))
    username_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    password_encrypted: Mapped[str | None] = mapped_column(Text)
    session_data_encrypted: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_login_at: Mapped[str | None] = mapped_column(String(50))

    person: Mapped["Person"] = relationship(back_populates="site_accounts")
