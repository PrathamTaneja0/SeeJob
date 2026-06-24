"""LLM field mapping — minimized DOM + profile JSON to selector→value map."""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from seejob.core.config import Settings, get_settings
from seejob.core.exceptions import LLMUnavailableError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a precise form-filling assistant. You will receive two inputs:

1. A minimized DOM description listing all interactive form fields on a web page, each with its CSS selector, label, placeholder, type, and available options.
2. A user profile JSON containing the applicant's personal and professional information.

Your task: Match the fields to the appropriate user profile data. Output ONLY a flat JSON object where:
- Keys are valid Playwright CSS selectors (exactly as provided in the field descriptions)
- Values are the corresponding text data from the user profile that should be entered into each field

Rules:
- For select/dropdown fields, the value must exactly match one of the available option values listed
- For checkboxes, use "true" or "false"
- For date fields, use ISO 8601 format (YYYY-MM-DD)
- If a field cannot be confidently matched to any user profile data, omit it from the output
- Do not include markdown code block backticks or conversational text
- Do not include any explanation, just the raw JSON object
- For file upload fields, omit them from the output"""


class FieldMapper(ABC):
    """Maps form fields to profile values via LLM."""

    @abstractmethod
    async def map_fields(self, minimized_dom: str, profile: dict[str, Any]) -> dict[str, str]:
        """Return flat selector→value mapping for standard fields."""


def parse_mapping_json(raw: str) -> dict[str, str]:
    """Parse LLM mapping response, stripping markdown fences if present."""
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Mapping response must be a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def rule_based_field_map(
    minimized_dom: str,
    profile: dict[str, Any],
) -> dict[str, str]:
    """Regex keyword fallback when LLM is unavailable."""
    mapping: dict[str, str] = {}
    email = profile.get("email", "")
    name = profile.get("full_name") or profile.get("name", "")
    phone = profile.get("phone", "")
    linkedin = profile.get("linkedin_url", "")

    for line in minimized_dom.splitlines():
        if "selector=" not in line:
            continue
        selector_match = re.search(r'selector="([^"]+)"', line)
        if not selector_match:
            continue
        selector = selector_match.group(1)
        lower = line.lower()

        if email and any(k in lower for k in ("email", "e-mail")):
            mapping[selector] = email
        elif name and any(k in lower for k in ("full name", "fullname", 'name="name"', "first and last")):
            mapping[selector] = name
        elif phone and any(k in lower for k in ("phone", "mobile", "tel")):
            mapping[selector] = phone
        elif linkedin and "linkedin" in lower:
            mapping[selector] = linkedin

    return mapping


class OpenAIFieldMapper(FieldMapper):
    """Map fields via OpenAI-compatible chat API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def map_fields(self, minimized_dom: str, profile: dict[str, Any]) -> dict[str, str]:
        if not self._settings.openai_api_key:
            raise LLMUnavailableError("SEEJOB_OPENAI_API_KEY is required for field mapping")

        user_message = (
            f"Here is the minimized DOM of the current page form fields:\n\n"
            f"{minimized_dom}\n\n"
            f"Here is the user profile JSON:\n\n"
            f"{json.dumps(profile, indent=2, default=str)}\n\n"
            "Generate the selector-to-value mapping JSON."
        )

        payload = {
            "model": self._settings.llm_model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._settings.openai_base_url.rstrip('/')}/chat/completions"

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        raw = data["choices"][0]["message"]["content"]
        try:
            return parse_mapping_json(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("LLM mapping parse failed; falling back to rule-based mapper")
            return rule_based_field_map(minimized_dom, profile)


class MockFieldMapper(FieldMapper):
    """Deterministic mapper for tests (SEEJOB_ALLOW_MOCK_LLM only)."""

    async def map_fields(self, minimized_dom: str, profile: dict[str, Any]) -> dict[str, str]:
        return rule_based_field_map(minimized_dom, profile)
