"""Browser automation interfaces — actuator layer (Phase 2+)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class BrowserActionResult(str, Enum):
    """Outcome of a browser automation action."""

    SUCCESS = "success"
    AUTH_REQUIRED = "auth_required"
    CAPTCHA = "captcha"
    NEEDS_MANUAL = "needs_manual"
    FAILED = "failed"


@dataclass
class BrowserSession:
    """Persistent browser session for ATS cookie storage."""

    profile_dir: Path
    domain: str
    cookies_encrypted: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FormField:
    """Detected form field on an ATS page."""

    selector: str
    name: str
    field_type: str
    label: str | None = None
    required: bool = False
    options: list[str] = field(default_factory=list)


@dataclass
class FillResult:
    """Result of filling an application form."""

    result: BrowserActionResult
    fields_filled: int = 0
    message: str | None = None
    screenshot_path: str | None = None


class BrowserActuator(ABC):
    """Interface for browser-based form filling (Playwright implementation in Phase 2)."""

    @abstractmethod
    async def launch(self, session: BrowserSession) -> None:
        """Launch browser with persisted profile/cookies."""

    @abstractmethod
    async def navigate(self, url: str) -> BrowserActionResult:
        """Navigate to a URL and detect blockers (captcha, login)."""

    @abstractmethod
    async def detect_form_fields(self) -> list[FormField]:
        """Detect fillable fields on the current page."""

    @abstractmethod
    async def fill_fields(self, field_values: dict[str, str]) -> FillResult:
        """Fill form fields with provided values."""

    @abstractmethod
    async def upload_file(self, selector: str, file_path: Path) -> BrowserActionResult:
        """Upload a document to a file input."""

    @abstractmethod
    async def submit_form(self) -> BrowserActionResult:
        """Submit the application form (requires prior approval gate)."""

    @abstractmethod
    async def save_session(self) -> BrowserSession:
        """Persist cookies and session state for ATS reuse."""

    @abstractmethod
    async def close(self) -> None:
        """Close browser and release resources."""
