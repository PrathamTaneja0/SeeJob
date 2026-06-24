"""CapSolver integration for Turnstile and reCAPTCHA v2."""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

from seejob.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

CAPSOLVER_CREATE_URL = "https://api.capsolver.com/createTask"
CAPSOLVER_RESULT_URL = "https://api.capsolver.com/getTaskResult"
POLL_INTERVAL_SEC = 2.0
MAX_POLL_ATTEMPTS = 30

CaptchaType = Literal["turnstile", "recaptcha_v2"]


class CapSolverError(Exception):
    """Raised when CapSolver API returns an error."""


def _api_key(settings: Settings | None = None) -> str | None:
    key = (settings or get_settings()).capsolver_api_key
    return key if key else None


def _create_task(client: httpx.Client, api_key: str, task: dict[str, Any]) -> str:
    response = client.post(
        CAPSOLVER_CREATE_URL,
        json={"clientKey": api_key, "task": task},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("errorId"):
        raise CapSolverError(data.get("errorDescription", "createTask failed"))
    task_id = data.get("taskId")
    if not task_id:
        raise CapSolverError("No taskId in CapSolver response")
    return task_id


def _poll_result(client: httpx.Client, api_key: str, task_id: str) -> str | None:
    import time

    for _ in range(MAX_POLL_ATTEMPTS):
        response = client.post(
            CAPSOLVER_RESULT_URL,
            json={"clientKey": api_key, "taskId": task_id},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("errorId"):
            raise CapSolverError(data.get("errorDescription", "getTaskResult failed"))
        status = data.get("status")
        if status == "ready":
            solution = data.get("solution") or {}
            return solution.get("gRecaptchaResponse") or solution.get("token")
        if status == "failed":
            return None
        time.sleep(POLL_INTERVAL_SEC)
    return None


def solve_captcha(
    captcha_type: CaptchaType,
    *,
    website_url: str,
    website_key: str,
    settings: Settings | None = None,
) -> str | None:
    """Solve a captcha and return the token, or None if unavailable/failed."""
    api_key = _api_key(settings)
    if not api_key:
        logger.debug("CapSolver API key not configured")
        return None

    if captcha_type == "turnstile":
        task: dict[str, Any] = {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": website_url,
            "websiteKey": website_key,
        }
    else:
        task = {
            "type": "ReCaptchaV2TaskProxyLess",
            "websiteURL": website_url,
            "websiteKey": website_key,
        }

    try:
        with httpx.Client() as client:
            task_id = _create_task(client, api_key, task)
            return _poll_result(client, api_key, task_id)
    except (httpx.HTTPError, CapSolverError) as exc:
        logger.warning("CapSolver solve failed: %s", exc)
        return None


def solve_turnstile(website_url: str, website_key: str, *, settings: Settings | None = None) -> str | None:
    """Solve Cloudflare Turnstile."""
    return solve_captcha("turnstile", website_url=website_url, website_key=website_key, settings=settings)


def solve_recaptcha_v2(
    website_url: str, website_key: str, *, settings: Settings | None = None
) -> str | None:
    """Solve Google reCAPTCHA v2."""
    return solve_captcha("recaptcha_v2", website_url=website_url, website_key=website_key, settings=settings)
