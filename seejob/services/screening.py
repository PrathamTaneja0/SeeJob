"""Screening answer utilities."""

import hashlib
import re


def normalize_question(question: str) -> str:
    """Normalize question text for consistent hashing."""
    text = question.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s?]", "", text)
    return text


def hash_question(question: str) -> str:
    """Compute SHA-256 hash of normalized question for Q&A bank caching."""
    normalized = normalize_question(question)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
