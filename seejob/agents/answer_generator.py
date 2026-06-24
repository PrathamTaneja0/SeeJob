"""LLM answer generation for screening questions with RAG context."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

from seejob.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

ANSWER_SYSTEM_PROMPT = """You are helping a job applicant answer screening questions.

Rules:
- Answer in first person as the applicant.
- Use ONLY facts from the provided profile context.
- Do NOT invent employers, projects, or achievements.
- Keep answers concise (under 200 words) unless the question requires more detail.
- If context is insufficient, say what you can truthfully answer and avoid fabrication.
"""


class AnswerGenerator(ABC):
    """Interface for generating screening answers."""

    @abstractmethod
    async def generate(self, question: str, context: str) -> str:
        """Generate an answer using retrieved profile context."""


class OpenAIAnswerGenerator(AnswerGenerator):
    """Generate answers via OpenAI-compatible API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def generate(self, question: str, context: str) -> str:
        if not self._settings.openai_api_key:
            raise ValueError("SEEJOB_OPENAI_API_KEY is required for answer generation")

        user_prompt = (
            f"Question: {question}\n\n"
            f"Profile context:\n{context[:12000]}"
        )

        payload = {
            "model": self._settings.llm_model,
            "temperature": 0.4,
            "messages": [
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self._settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._settings.openai_base_url.rstrip('/')}/chat/completions"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"].strip()


class MockAnswerGenerator(AnswerGenerator):
    """Deterministic generator for tests."""

    async def generate(self, question: str, context: str) -> str:
        return f"Based on my experience: {context[:100]}... (answer to: {question[:50]})"
