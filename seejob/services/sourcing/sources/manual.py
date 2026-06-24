"""Manual URL job source — scrape a single posting URL."""

from __future__ import annotations

import httpx

from seejob.services.sourcing.base import JobSource, RawJob
from seejob.services.sourcing.parser import parse_job_html

_DEFAULT_HEADERS = {
    "User-Agent": "SeeJob/0.1 (job sourcing; +https://github.com/seejob)",
    "Accept": "text/html,application/xhtml+xml",
}


class ManualUrlSource(JobSource):
    """Fetch and parse one job posting URL."""

    name = "manual_url"

    def __init__(self, url: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._url = url
        self._client = client
        self._owns_client = client is None

    async def fetch_new_jobs(self) -> list[RawJob]:
        """Scrape title, company, and JD from the configured URL."""
        if self._client is not None:
            return await self._fetch(self._client)

        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers=_DEFAULT_HEADERS,
        ) as client:
            return await self._fetch(client)

    async def _fetch(self, client: httpx.AsyncClient) -> list[RawJob]:
        response = await client.get(self._url)
        response.raise_for_status()
        parsed = parse_job_html(response.text, self._url)
        return [
            RawJob(
                url=self._url,
                title=parsed["title"],
                company=parsed["company"],
                location=parsed.get("location"),
                is_remote=parsed.get("is_remote", False),
                jd_text=parsed.get("jd_text"),
                source=self.name,
            )
        ]
