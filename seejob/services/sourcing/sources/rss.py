"""RSS/Atom feed job source."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import httpx

from seejob.services.sourcing.base import JobSource, RawJob
from seejob.services.sourcing.parser import parse_job_html

_DEFAULT_HEADERS = {
    "User-Agent": "SeeJob/0.1 (job sourcing; +https://github.com/seejob)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
}

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def _parse_rss_items(xml_text: str) -> list[dict[str, str]]:
    """Parse RSS 2.0 or Atom feed entries into link/title/summary dicts."""
    root = ET.fromstring(xml_text)
    items: list[dict[str, str]] = []

    if root.tag.endswith("feed"):
        for entry in root.findall("atom:entry", _ATOM_NS):
            link_el = entry.find("atom:link[@rel='alternate']", _ATOM_NS)
            if link_el is None:
                link_el = entry.find("atom:link", _ATOM_NS)
            link = link_el.get("href", "") if link_el is not None else ""
            title_el = entry.find("atom:title", _ATOM_NS)
            summary_el = entry.find("atom:summary", _ATOM_NS) or entry.find(
                "atom:content", _ATOM_NS
            )
            items.append(
                {
                    "link": link,
                    "title": (title_el.text or "").strip() if title_el is not None else "",
                    "summary": (summary_el.text or "").strip() if summary_el is not None else "",
                }
            )
        return items

    channel = root.find("channel")
    if channel is None:
        return items

    for item in channel.findall("item"):
        link_el = item.find("link")
        title_el = item.find("title")
        desc_el = item.find("description")
        if desc_el is None:
            desc_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
        items.append(
            {
                "link": (link_el.text or "").strip() if link_el is not None else "",
                "title": (title_el.text or "").strip() if title_el is not None else "",
                "summary": (desc_el.text or "").strip() if desc_el is not None else "",
            }
        )
    return items


class RssJobSource(JobSource):
    """Poll configured RSS/Atom feeds for new job links."""

    name = "rss"

    def __init__(
        self,
        feed_urls: list[str],
        *,
        client: httpx.AsyncClient | None = None,
        enrich_html: bool = True,
    ) -> None:
        self._feed_urls = feed_urls
        self._client = client
        self._enrich_html = enrich_html

    async def fetch_new_jobs(self) -> list[RawJob]:
        """Fetch entries from all configured feeds."""
        if self._client is not None:
            return await self._fetch_all(self._client)

        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers=_DEFAULT_HEADERS,
        ) as client:
            return await self._fetch_all(client)

    async def _fetch_all(self, client: httpx.AsyncClient) -> list[RawJob]:
        jobs: list[RawJob] = []
        seen_urls: set[str] = set()

        for feed_url in self._feed_urls:
            try:
                response = await client.get(feed_url)
                response.raise_for_status()
            except httpx.HTTPError:
                continue

            for entry in _parse_rss_items(response.text):
                link = entry.get("link", "").strip()
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)

                title = entry.get("title") or "Untitled Role"
                summary = _strip_html(entry.get("summary", ""))

                if self._enrich_html and link.startswith("http"):
                    try:
                        page = await client.get(link)
                        page.raise_for_status()
                        parsed = parse_job_html(page.text, link)
                        jobs.append(
                            RawJob(
                                url=link,
                                title=parsed["title"] or title,
                                company=parsed["company"],
                                location=parsed.get("location"),
                                is_remote=parsed.get("is_remote", False),
                                jd_text=parsed.get("jd_text") or summary or None,
                                source=self.name,
                            )
                        )
                        continue
                    except httpx.HTTPError:
                        pass

                company = link.split("/")[2].replace("www.", "").split(".")[0].title()
                jobs.append(
                    RawJob(
                        url=link,
                        title=title[:500],
                        company=company,
                        jd_text=summary or None,
                        source=self.name,
                    )
                )
        return jobs
