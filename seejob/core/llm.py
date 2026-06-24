"""Resolve LLM-backed services with production-safe mock guards."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from seejob.agents.answer_generator import AnswerGenerator, OpenAIAnswerGenerator
from seejob.agents.document_generator import DocumentGenerator, OpenAIDocumentGenerator
from seejob.agents.profile_extractor import OpenAIProfileExtractor, ProfileExtractor
from seejob.core.config import Settings, get_settings
from seejob.core.exceptions import LLMUnavailableError

if TYPE_CHECKING:
    from seejob.browser.field_mapper import FieldMapper

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


def resolve_document_generator(
    generator: DocumentGenerator | None = None,
    *,
    settings: Settings | None = None,
) -> DocumentGenerator:
    """Return injected generator, OpenAI generator, or dev-only mock."""
    if generator is not None:
        return generator

    cfg = settings or get_settings()
    if cfg.openai_api_key:
        return OpenAIDocumentGenerator(cfg)

    if cfg.can_use_mock_llm:
        from seejob.agents.document_generator import MockDocumentGenerator

        logger.warning("Using MockDocumentGenerator (SEEJOB_ALLOW_MOCK_LLM=true)")
        return MockDocumentGenerator()

    raise LLMUnavailableError(_MISSING_KEY_MESSAGE)


def resolve_field_mapper(
    mapper: FieldMapper | None = None,
    *,
    settings: Settings | None = None,
) -> FieldMapper:
    """Return injected mapper, OpenAI mapper, or dev-only mock."""
    from seejob.browser.field_mapper import MockFieldMapper, OpenAIFieldMapper

    if mapper is not None:
        return mapper

    cfg = settings or get_settings()
    if cfg.openai_api_key:
        return OpenAIFieldMapper(cfg)

    if cfg.allow_mock_llm:
        logger.warning("Using MockFieldMapper (SEEJOB_ALLOW_MOCK_LLM=true)")
        return MockFieldMapper()

    raise LLMUnavailableError(_MISSING_KEY_MESSAGE)
