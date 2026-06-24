"""Shared application exceptions."""


class LLMUnavailableError(RuntimeError):
    """Raised when an LLM-backed feature is used without API credentials."""


class UnsupportedMediaTypeError(ValueError):
    """Raised when an uploaded file type is not supported."""


class URLValidationError(ValueError):
    """Raised when a URL fails SSRF or allowlist validation."""
