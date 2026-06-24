"""Stub board API source for future JobSpy/Remotive-style integrations."""

from seejob.services.sourcing.base import JobSource, RawJob


class BoardApiSource(JobSource):
    """Placeholder for third-party job board API adapters."""

    name = "board_api"

    def __init__(self, board: str = "generic") -> None:
        self._board = board

    async def fetch_new_jobs(self) -> list[RawJob]:
        """Not implemented — returns empty list until Phase 3+."""
        return []
