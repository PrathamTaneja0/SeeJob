"""HTML job posting parser — extract title, company, location, JD."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

REMOTE_KEYWORDS = re.compile(
    r"\b(remote|work from home|wfh|distributed|anywhere)\b",
    re.IGNORECASE,
)


class _HTMLTextExtractor(HTMLParser):
    """Collect visible text from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _extract_with_readability(html: str) -> str | None:
    """Try readability-lxml for main content extraction."""
    try:
        from readability import Document

        doc = Document(html)
        summary_html = doc.summary()
        if not summary_html:
            return None
        parser = _HTMLTextExtractor()
        parser.feed(summary_html)
        text = parser.get_text().strip()
        return text or None
    except ImportError:
        return None
    except Exception:
        return None


def _extract_json_ld(html: str) -> dict[str, Any] | None:
    """Parse JobPosting JSON-LD if present."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            raw = script.string or script.get_text()
            if not raw:
                continue
            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type", "")
                types = item_type if isinstance(item_type, list) else [item_type]
                if any(t == "JobPosting" for t in types):
                    return item
    except Exception:
        return None
    return None


def _title_from_json_ld(data: dict[str, Any]) -> str | None:
    title = data.get("title")
    return str(title).strip() if title else None


def _company_from_json_ld(data: dict[str, Any]) -> str | None:
    org = data.get("hiringOrganization") or data.get("employer")
    if isinstance(org, dict):
        name = org.get("name")
        return str(name).strip() if name else None
    if isinstance(org, str):
        return org.strip()
    return None


def _location_from_json_ld(data: dict[str, Any]) -> tuple[str | None, bool]:
    location = data.get("jobLocation")
    remote_flag = bool(data.get("jobLocationType") == "TELECOMMUTE")
    if isinstance(location, list):
        location = location[0] if location else None
    if isinstance(location, dict):
        address = location.get("address", {})
        if isinstance(address, dict):
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            ]
            loc = ", ".join(str(p) for p in parts if p)
            return loc or None, remote_flag
    return None, remote_flag


def _title_from_html(html: str) -> str | None:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
            for suffix in (" | LinkedIn", " - Indeed", " | Glassdoor"):
                if title.endswith(suffix):
                    title = title[: -len(suffix)].strip()
            return title or None
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return str(og["content"]).strip()
    except Exception:
        return None
    return None


def _company_from_url(url: str) -> str:
    """Fallback company name from job board hostname."""
    host = urlparse(url).netloc.lower()
    host = host.removeprefix("www.")
    return host.split(".")[0].replace("-", " ").title() or "Unknown"


def _detect_remote(location: str | None, text: str) -> bool:
    haystack = " ".join(filter(None, [location, text[:2000]]))
    return bool(REMOTE_KEYWORDS.search(haystack))


def parse_job_html(html: str, url: str) -> dict[str, Any]:
    """Extract structured job fields from HTML."""
    json_ld = _extract_json_ld(html)
    title = _title_from_json_ld(json_ld) if json_ld else None
    company = _company_from_json_ld(json_ld) if json_ld else None
    location: str | None = None
    is_remote = False

    if json_ld:
        location, is_remote = _location_from_json_ld(json_ld)
        if not title:
            title = _title_from_json_ld(json_ld)
        jd_text = json_ld.get("description")
        if isinstance(jd_text, str):
            jd_text = re.sub(r"<[^>]+>", " ", jd_text)
            jd_text = re.sub(r"\s+", " ", jd_text).strip()
        else:
            jd_text = None
    else:
        jd_text = None

    if not title:
        title = _title_from_html(html)
    if not company:
        company = _company_from_url(url)

    if not jd_text:
        jd_text = _extract_with_readability(html)
    if not jd_text:
        parser = _HTMLTextExtractor()
        parser.feed(html)
        jd_text = re.sub(r"\n{3,}", "\n\n", parser.get_text()).strip() or None

    if not location and jd_text:
        loc_match = re.search(
            r"(?:location|based in)[:\s]+([A-Za-z][A-Za-z\s,]{2,40})",
            jd_text[:1500],
            re.IGNORECASE,
        )
        if loc_match:
            location = loc_match.group(1).strip()

    if not is_remote:
        is_remote = _detect_remote(location, jd_text or "")

    return {
        "title": (title or "Untitled Role")[:500],
        "company": (company or "Unknown")[:255],
        "location": location[:255] if location else None,
        "is_remote": is_remote,
        "jd_text": jd_text,
    }
