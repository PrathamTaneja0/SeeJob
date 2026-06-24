"""Agent run audit log."""

import enum

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from seejob.models.base import Base, TimestampMixin


class AgentRunStatus(str, enum.Enum):
    """Status of a worker/agent execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRun(Base, TimestampMixin):
    """Audit log entry for orchestrator and worker executions."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    worker_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(
        Enum(AgentRunStatus, name="agent_run_status"),
        default=AgentRunStatus.PENDING,
        nullable=False,
        index=True,
    )
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[str | None] = mapped_column(String(50))
    finished_at: Mapped[str | None] = mapped_column(String(50))
    duration_ms: Mapped[int | None] = mapped_column()
