"""Job source adapter interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RawJob:
    """Unprocessed job discovered from an external source."""

    url: str
    title: str
    company: str
    location: str | None = None
    is_remote: bool = False
    jd_text: str | None = None
    source: str = "manual"


class JobSource(ABC):
    """Adapter that fetches newly discovered jobs from one source."""

    name: str = "base"

    @abstractmethod
    async def fetch_new_jobs(self) -> list[RawJob]:
        """Return newly discovered jobs from this source."""
