"""Screening question answer bank with hash-based caching."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seejob.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seejob.models.person import Person


class ScreeningAnswer(Base, TimestampMixin):
    """Cached Q&A for behavioral and screening questions.

    question_hash enables deduplication across similar phrasings.
    """

    __tablename__ = "screening_answers"
    __table_args__ = (
        UniqueConstraint("person_id", "question_hash", name="uq_person_question_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(100))
    times_used: Mapped[int] = mapped_column(default=0, nullable=False)

    person: Mapped["Person"] = relationship(back_populates="screening_answers")
