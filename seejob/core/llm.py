"""Resolve LLM-backed services with production-safe mock guards."""

from __future__ import annotations

import logging

from seejob.agents.answer_generator import AnswerGenerator, OpenAIAnswerGenerator
from seejob.agents.profile_extractor import OpenAIProfileExtractor, ProfileExtractor
from seejob.core.config import Settings, get_settings
from seejob.core.exceptions import LLMUnavailableError

logger = logging.getLogger(__name__)

_MISSING_KEY_MESSAGE = (
    "SEEJOB_OPENAI_API_KEY is required. "
    "Set SEEJOB_ALLOW_MOCK_LLM=true for local development only."
)


def resolve_profile_extractor(
    extractor: ProfileExtractor | None = None,
    *,
    settings: Settings | None = None,
) -> ProfileExtractor:
    """Return injected extractor, OpenAI extractor, or dev-only mock."""
    if extractor is not None:
        return extractor

    cfg = settings or get_settings()
    if cfg.openai_api_key:
        return OpenAIProfileExtractor(cfg)

    if cfg.allow_mock_llm:
        from seejob.agents.profile_extractor import MockProfileExtractor

        logger.warning("Using MockProfileExtractor (SEEJOB_ALLOW_MOCK_LLM=true)")
        return MockProfileExtractor()

    raise LLMUnavailableError(_MISSING_KEY_MESSAGE)


def resolve_answer_generator(
    generator: AnswerGenerator | None = None,
    *,
    settings: Settings | None = None,
) -> AnswerGenerator:
    """Return injected generator, OpenAI generator, or dev-only mock."""
    if generator is not None:
        return generator

    cfg = settings or get_settings()
    if cfg.openai_api_key:
        return OpenAIAnswerGenerator(cfg)

    if cfg.allow_mock_llm:
        from seejob.agents.answer_generator import MockAnswerGenerator

        logger.warning("Using MockAnswerGenerator (SEEJOB_ALLOW_MOCK_LLM=true)")
        return MockAnswerGenerator()

    raise LLMUnavailableError(_MISSING_KEY_MESSAGE)
