"""ATS procedural memory per domain."""

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from seejob.models.base import Base, TimestampMixin


class ATSLearning(Base, TimestampMixin):
    """Per-domain procedural memory for form filling and navigation."""

    __tablename__ = "ats_learnings"
    __table_args__ = (UniqueConstraint("domain", "procedure_key", name="uq_domain_procedure"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    procedure_key: Mapped[str] = mapped_column(String(255), nullable=False)
    procedure_data: Mapped[str] = mapped_column(Text, nullable=False)
    success_count: Mapped[int] = mapped_column(default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
