"""Background worker placeholders — scheduled sourcing (Phase 1+)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class WorkerStatus(str, Enum):
    """Worker execution status."""

    IDLE = "idle"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkerResult:
    """Result from a background worker run."""

    worker_name: str
    status: WorkerStatus
    items_processed: int = 0
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class BaseWorker(ABC):
    """Base class for scheduled background workers."""

    name: str = "base_worker"

    @abstractmethod
    async def run(self) -> WorkerResult:
        """Execute the worker task."""


class SourcingWorker(BaseWorker):
    """Scheduled job sourcing worker — runs on cron, not 24/7."""

    name = "sourcing_worker"

    async def run(self) -> WorkerResult:
        """Placeholder: discover jobs from configured sources on schedule."""
        return WorkerResult(
            worker_name=self.name,
            status=WorkerStatus.COMPLETED,
            items_processed=0,
            message="Sourcing worker not yet implemented (Phase 1)",
        )


class ScoringWorker(BaseWorker):
    """Score newly discovered jobs against profile."""

    name = "scoring_worker"

    async def run(self) -> WorkerResult:
        """Placeholder: score jobs in discovered state."""
        return WorkerResult(
            worker_name=self.name,
            status=WorkerStatus.COMPLETED,
            items_processed=0,
            message="Scoring worker not yet implemented (Phase 1)",
        )
