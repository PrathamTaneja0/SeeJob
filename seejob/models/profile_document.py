"""Supporting documents attached to a person profile."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seejob.models.base import Base

if TYPE_CHECKING:
    from seejob.models.person import Person


class ProfileDocument(Base):
    """Uploaded supplementary document (portfolio, certs, cover letter template, etc.)."""

    __tablename__ = "profile_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    label: Mapped[str | None] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    person: Mapped["Person"] = relationship(back_populates="profile_documents")
