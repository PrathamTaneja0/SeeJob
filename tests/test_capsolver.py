"""Tests for CapSolver integration (mocked HTTP)."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from seejob.integrations.capsolver import (
    CapSolverError,
    solve_captcha,
    solve_recaptcha_v2,
    solve_turnstile,
)


def test_solve_captcha_no_api_key() -> None:
    with patch("seejob.integrations.capsolver._api_key", return_value=None):
        assert solve_turnstile("https://example.com", "site-key") is None


def test_solve_turnstile_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEEJOB_CAPSOLVER_API_KEY", "test-key")
    from seejob.core.config import get_settings

    get_settings.cache_clear()

    create_resp = MagicMock()
    create_resp.json.return_value = {"errorId": 0, "taskId": "task-1"}
    create_resp.raise_for_status = MagicMock()

    result_resp = MagicMock()
    result_resp.json.return_value = {
        "errorId": 0,
        "status": "ready",
        "solution": {"token": "turnstile-token"},
    }
    result_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.side_effect = [create_resp, result_resp]

    with patch("httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = mock_client
        token = solve_turnstile("https://example.com", "site-key")

    assert token == "turnstile-token"
    get_settings.cache_clear()


def test_solve_recaptcha_v2_failed_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEEJOB_CAPSOLVER_API_KEY", "test-key")
    from seejob.core.config import get_settings

    get_settings.cache_clear()

    create_resp = MagicMock()
    create_resp.json.return_value = {"errorId": 0, "taskId": "task-2"}
    create_resp.raise_for_status = MagicMock()

    result_resp = MagicMock()
    result_resp.json.return_value = {"errorId": 0, "status": "failed"}
    result_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.side_effect = [create_resp, result_resp]

    with patch("httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = mock_client
        token = solve_recaptcha_v2("https://example.com", "recaptcha-key")

    assert token is None
    get_settings.cache_clear()


def test_solve_captcha_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEEJOB_CAPSOLVER_API_KEY", "test-key")
    from seejob.core.config import get_settings

    get_settings.cache_clear()

    with patch("httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post.side_effect = httpx.HTTPError("network")
        assert solve_captcha("turnstile", website_url="https://x.com", website_key="k") is None

    get_settings.cache_clear()
