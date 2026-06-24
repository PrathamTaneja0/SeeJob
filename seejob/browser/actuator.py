"""Playwright browser actuator — StockFish scrape-map-fill orchestration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seejob.browser.dom_extractor import reduce_dom, screening_textareas
from seejob.browser.field_mapper import FieldMapper
from seejob.browser.form_filler import FillOptions, fill_form, submit_form
from seejob.browser.interfaces import (
    BrowserActionResult,
    BrowserActuator,
    BrowserSession,
    FillResult,
    FormField,
)
from seejob.core.config import Settings, get_settings
from seejob.models.application import Application, DocumentType
from seejob.services.ats_learning import normalize_domain, store_apply_learning
from seejob.services.auth import (
    get_credentials,
    load_session_cookies,
    save_session_cookies,
    try_login,
)
from seejob.services.profile import get_person
from seejob.services.qa import get_or_generate_answer

logger = logging.getLogger(__name__)

CAPTCHA_SELECTORS = [
    'iframe[src*="recaptcha"]',
    'iframe[src*="hcaptcha"]',
    'iframe[src*="challenges.cloudflare.com"]',
    ".g-recaptcha",
    ".cf-turnstile",
    "#captcha",
    '[class*="captcha"]',
    '[class*="turnstile"]',
]

LOGIN_INDICATORS = [
    'input[type="password"]',
    'button:has-text("Sign in")',
    'button:has-text("Log in")',
    'a:has-text("Sign in")',
]


@dataclass
class ApplyFillResult:
    """High-level apply outcome from PlaywrightActuator.apply()."""

    result: BrowserActionResult
    fields_filled: int = 0
    message: str | None = None
    screenshot_path: str | None = None
    page_url: str | None = None


def person_to_profile_dict(person: Any) -> dict[str, Any]:
    """Serialize person ORM to JSON-friendly profile for field mapper."""
    return {
        "full_name": person.full_name,
        "email": person.email,
        "phone": person.phone,
        "location": person.location,
        "headline": person.headline,
        "summary": person.summary,
        "linkedin_url": person.linkedin_url,
        "github_url": person.github_url,
        "portfolio_url": person.portfolio_url,
        "work_authorization": (
            person.work_authorization.value if person.work_authorization else None
        ),
        "experiences": [
            {
                "company": exp.company,
                "title": exp.title,
                "start_date": str(exp.start_date),
                "end_date": str(exp.end_date) if exp.end_date else None,
                "is_current": exp.is_current,
                "description": exp.description,
            }
            for exp in person.experiences
        ],
        "education": [
            {
                "institution": edu.institution,
                "degree": edu.degree,
                "field_of_study": edu.field_of_study,
            }
            for edu in person.education
        ],
        "skills": [{"name": s.name, "level": s.level} for s in person.skills],
    }


class PlaywrightActuator(BrowserActuator):
    """Playwright implementation of BrowserActuator with apply() orchestration."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        field_mapper: FieldMapper | None = None,
        headless: bool = True,
    ) -> None:
        self._settings = settings or get_settings()
        self._field_mapper = field_mapper
        self._headless = headless
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._session: BrowserSession | None = None
        self._person_id: int | None = None
        self._application_id: int | None = None
        self._db: Session | None = None
        self._form_context: Any = None
        self._artifacts_dir = Path("seejob/data/artifacts/screenshots")

    async def apply(
        self,
        application_id: int,
        db: Session,
        *,
        dry_run: bool = True,
        submit: bool = False,
    ) -> ApplyFillResult:
        """Orchestrate: open URL → auth stub → extract → map → fill → screenshot."""
        app = db.scalar(
            select(Application)
            .where(Application.id == application_id)
            .options(
                selectinload(Application.job),
                selectinload(Application.documents),
            )
        )
        if app is None:
            return ApplyFillResult(
                result=BrowserActionResult.FAILED,
                message=f"Application {application_id} not found",
            )

        person = get_person(db, app.person_id)
        job_url = app.job.url
        domain = normalize_domain(job_url)

        self._person_id = app.person_id
        self._application_id = application_id
        self._db = db

        session = BrowserSession(
            profile_dir=self._settings.browser_profiles_dir / domain,
            domain=domain,
        )
        await self.launch(session, db=db, person_id=app.person_id)

        nav_result = await self.navigate(job_url)
        if nav_result != BrowserActionResult.SUCCESS:
            return ApplyFillResult(
                result=nav_result,
                message=f"Navigation blocked: {nav_result.value}",
                page_url=job_url,
            )

        blocker = await self._detect_and_resolve_blockers()
        if blocker != BrowserActionResult.SUCCESS:
            screenshot = await self._save_screenshot(application_id)
            return ApplyFillResult(
                result=blocker,
                message=f"Blocked: {blocker.value}",
                screenshot_path=screenshot,
                page_url=self._page.url if self._page else job_url,
            )

        dom = await reduce_dom(self._page)
        self._form_context = dom.form_context

        if not dom.fields:
            screenshot = await self._save_screenshot(application_id)
            store_apply_learning(
                db,
                domain=domain,
                fields_filled=0,
                fields_failed=0,
                dry_run=dry_run,
                success=False,
                notes="No form fields detected",
            )
            return ApplyFillResult(
                result=BrowserActionResult.NEEDS_MANUAL,
                message="No form fields detected on page",
                screenshot_path=screenshot,
                page_url=self._page.url,
            )

        from seejob.core.llm import resolve_field_mapper

        mapper = resolve_field_mapper(self._field_mapper, settings=self._settings)
        profile = person_to_profile_dict(person)
        mapping = await mapper.map_fields(dom.formatted, profile)

        for textarea in screening_textareas(dom.fields):
            qa = await get_or_generate_answer(db, textarea.label or "", person.id)
            mapping[textarea.selector] = qa.answer

        fill_options = self._document_paths(app)
        target = self._form_context or self._page
        fill_outcome = await fill_form(target, mapping, options=fill_options)

        if not dry_run and submit and fill_outcome.fields_filled > 0:
            submitted = await submit_form(self._page)
            if not submitted:
                logger.warning("Submit button not found for application %s", application_id)

        await self.save_session()
        screenshot = await self._save_screenshot(application_id)

        success = fill_outcome.fields_filled > 0 and not fill_outcome.failed
        store_apply_learning(
            db,
            domain=domain,
            fields_filled=fill_outcome.fields_filled,
            fields_failed=len(fill_outcome.failed),
            dry_run=dry_run,
            success=success,
            notes=f"Filled {fill_outcome.fields_filled} fields"
            + (f", {len(fill_outcome.failed)} failed" if fill_outcome.failed else ""),
        )

        result = BrowserActionResult.SUCCESS if success else BrowserActionResult.NEEDS_MANUAL
        return ApplyFillResult(
            result=result,
            fields_filled=fill_outcome.fields_filled,
            message="Dry run: form mapped and filled, submit skipped"
            if dry_run
            else f"Filled {fill_outcome.fields_filled} fields",
            screenshot_path=screenshot,
            page_url=self._page.url,
        )

    async def launch(
        self,
        session: BrowserSession,
        *,
        db: Session | None = None,
        person_id: int | None = None,
    ) -> None:
        """Launch browser with persisted profile/cookies."""
        from playwright.async_api import async_playwright

        self._session = session
        self._db = db
        self._person_id = person_id
        session.profile_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context()
        await self._load_cookies(session, db=db, person_id=person_id)
        self._page = await self._context.new_page()

    async def navigate(self, url: str) -> BrowserActionResult:
        """Navigate to URL and detect blockers."""
        if self._page is None:
            return BrowserActionResult.FAILED
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return BrowserActionResult.SUCCESS
        except Exception as exc:
            logger.warning("Navigation failed: %s", exc)
            return BrowserActionResult.FAILED

    async def detect_form_fields(self) -> list[FormField]:
        """Detect fillable fields on the current page."""
        if self._page is None:
            return []
        dom = await reduce_dom(self._page)
        self._form_context = dom.form_context
        return [f.to_form_field() for f in dom.fields]

    async def fill_fields(self, field_values: dict[str, str]) -> FillResult:
        """Fill form fields with provided values."""
        target = self._form_context or self._page
        if target is None:
            return FillResult(result=BrowserActionResult.FAILED, message="No page context")
        outcome = await fill_form(target, field_values)
        result = BrowserActionResult.SUCCESS if outcome.filled else BrowserActionResult.FAILED
        return FillResult(
            result=result,
            fields_filled=outcome.fields_filled,
            message=f"{len(outcome.failed)} fields failed" if outcome.failed else None,
        )

    async def upload_file(self, selector: str, file_path: Path) -> BrowserActionResult:
        """Upload a document to a file input."""
        target = self._form_context or self._page
        if target is None:
            return BrowserActionResult.FAILED
        try:
            await target.set_input_files(selector, str(file_path))
            return BrowserActionResult.SUCCESS
        except Exception:
            return BrowserActionResult.FAILED

    async def submit_form(self) -> BrowserActionResult:
        """Submit the application form."""
        if self._page is None:
            return BrowserActionResult.FAILED
        if await submit_form(self._page):
            return BrowserActionResult.SUCCESS
        return BrowserActionResult.NEEDS_MANUAL

    async def save_session(self) -> BrowserSession:
        """Persist cookies per domain and sync to SiteAccount."""
        if self._context is None or self._session is None:
            raise RuntimeError("Browser not launched")
        cookies = await self._context.cookies()
        cookie_path = self._session.profile_dir / "cookies.json"
        cookie_path.write_text(json.dumps(cookies), encoding="utf-8")
        self._session.metadata["cookie_count"] = len(cookies)
        if self._db is not None and self._person_id is not None:
            save_session_cookies(self._db, self._person_id, self._session.domain, cookies)
        return self._session

    async def close(self) -> None:
        """Close browser and release resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._person_id = None
        self._application_id = None
        self._db = None

    async def _load_cookies(
        self,
        session: BrowserSession,
        *,
        db: Session | None = None,
        person_id: int | None = None,
    ) -> None:
        cookies: list[dict[str, Any]] | None = None
        if db is not None and person_id is not None:
            cookies = load_session_cookies(db, person_id, session.domain)
        cookie_path = session.profile_dir / "cookies.json"
        if cookies is None and cookie_path.exists():
            try:
                cookies = json.loads(cookie_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug("Could not load cookies for %s: %s", session.domain, exc)
        if cookies and self._context is not None:
            try:
                await self._context.add_cookies(cookies)
            except Exception as exc:
                logger.debug("Could not add cookies for %s: %s", session.domain, exc)

    async def _detect_and_resolve_blockers(self) -> BrowserActionResult:
        """Detect captcha/login blockers and attempt automated resolution."""
        captcha = await self._detect_captcha()
        if captcha:
            solved = await self._try_solve_captcha()
            if not solved:
                return BrowserActionResult.CAPTCHA

        auth = await self._detect_auth_required()
        if auth:
            logged_in = await self._try_auth_login()
            if not logged_in:
                return BrowserActionResult.AUTH_REQUIRED

        return BrowserActionResult.SUCCESS

    async def _detect_captcha(self) -> bool:
        if self._page is None:
            return False
        for selector in CAPTCHA_SELECTORS:
            if await self._page.query_selector(selector):
                return True
        page_text = (await self._page.content()).lower()
        return "captcha" in page_text and ("recaptcha" in page_text or "turnstile" in page_text)

    async def _detect_auth_required(self) -> bool:
        if self._page is None:
            return False
        for selector in LOGIN_INDICATORS:
            if await self._page.query_selector(selector):
                return True
        return False

    async def _try_solve_captcha(self) -> bool:
        """Attempt CapSolver when API key is configured."""
        if self._page is None:
            return False
        from seejob.integrations.capsolver import solve_recaptcha_v2, solve_turnstile

        page_url = self._page.url
        site_key = await self._page.evaluate(
            """() => {
                const turnstile = document.querySelector('[data-sitekey]');
                if (turnstile) return turnstile.getAttribute('data-sitekey');
                const recaptcha = document.querySelector('.g-recaptcha');
                if (recaptcha) return recaptcha.getAttribute('data-sitekey');
                return null;
            }"""
        )
        if not site_key:
            return False

        is_turnstile = await self._page.query_selector(".cf-turnstile, iframe[src*='turnstile']")
        token = (
            solve_turnstile(page_url, site_key, settings=self._settings)
            if is_turnstile
            else solve_recaptcha_v2(page_url, site_key, settings=self._settings)
        )
        if not token:
            return False

        await self._page.evaluate(
            """(token) => {
                const textarea = document.querySelector('[name="g-recaptcha-response"]')
                    || document.querySelector('[name="cf-turnstile-response"]');
                if (textarea) textarea.value = token;
            }""",
            token,
        )
        await self._page.wait_for_timeout(1500)
        return not await self._detect_captcha()

    async def _try_auth_login(self) -> bool:
        """Attempt login with stored credentials and OTP."""
        if self._page is None or self._db is None or self._person_id is None or self._session is None:
            return False
        credentials = get_credentials(self._db, self._person_id, self._session.domain)
        if credentials is None:
            return False
        success = await try_login(
            self._page,
            credentials,
            domain=self._session.domain,
            application_id=self._application_id,
        )
        if success:
            await self.save_session()
        return success

    async def _detect_blockers(self) -> BrowserActionResult:
        if self._page is None:
            return BrowserActionResult.FAILED

        for selector in CAPTCHA_SELECTORS:
            if await self._page.query_selector(selector):
                return BrowserActionResult.CAPTCHA

        page_text = (await self._page.content()).lower()
        if "captcha" in page_text and "recaptcha" in page_text:
            return BrowserActionResult.CAPTCHA

        for selector in LOGIN_INDICATORS:
            if await self._page.query_selector(selector):
                return BrowserActionResult.AUTH_REQUIRED

        return BrowserActionResult.SUCCESS

    async def _save_screenshot(self, application_id: int) -> str | None:
        if self._page is None:
            return None
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = self._artifacts_dir / f"app_{application_id}_{ts}.png"
        try:
            await self._page.screenshot(path=str(path), full_page=True)
            return str(path)
        except Exception as exc:
            logger.debug("Screenshot failed: %s", exc)
            return None

    def _document_paths(self, app: Application) -> FillOptions:
        resume: Path | None = None
        cover: Path | None = None
        for doc in app.documents:
            if doc.pdf_path:
                p = Path(doc.pdf_path)
                if doc.doc_type == DocumentType.CV:
                    resume = p
                elif doc.doc_type == DocumentType.COVER_LETTER:
                    cover = p
        return FillOptions(resume_path=resume, cover_letter_path=cover)
