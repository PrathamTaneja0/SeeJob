"""Tests for auth service and site account management."""

from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from seejob.core.security import encrypt_value
from seejob.models.person import Person, WorkAuthorization
from seejob.models.site_account import SiteAccount
from seejob.schemas.site_account import SiteAccountCreate
from seejob.services.auth import (
    get_credentials,
    load_session_cookies,
    mask_secret,
    peek_manual_otp,
    pop_manual_otp,
    resolve_otp,
    save_session_cookies,
    store_manual_otp,
    try_login,
)
from seejob.services.site_account import create_site_account, list_site_accounts


@pytest.fixture
def fernet_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("SEEJOB_FERNET_KEY", key)
    from seejob.core.config import get_settings

    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


@pytest.fixture
def person(db_session) -> Person:
    p = Person(
        full_name="Test User",
        email="test@example.com",
        work_authorization=WorkAuthorization.CITIZEN,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def test_mask_secret() -> None:
    assert mask_secret("secret123") == "****"
    assert mask_secret(None) == "****"
    assert mask_secret("abcdef", visible=2) == "ab****"


def test_get_credentials_decrypts(db_session, person, fernet_key) -> None:
    account = SiteAccount(
        person_id=person.id,
        platform="greenhouse",
        domain="boards.greenhouse.io",
        username_encrypted=encrypt_value("user@example.com"),
        password_encrypted=encrypt_value("s3cret"),
    )
    db_session.add(account)
    db_session.commit()

    creds = get_credentials(db_session, person.id, "boards.greenhouse.io")
    assert creds is not None
    assert creds.username == "user@example.com"
    assert creds.password == "s3cret"


def test_session_cookies_round_trip(db_session, person, fernet_key) -> None:
    account = SiteAccount(
        person_id=person.id,
        platform="lever",
        domain="jobs.lever.co",
        username_encrypted=encrypt_value("u@x.com"),
        password_encrypted=encrypt_value("pw"),
    )
    db_session.add(account)
    db_session.commit()

    cookies = [{"name": "session", "value": "abc", "domain": "jobs.lever.co", "path": "/"}]
    save_session_cookies(db_session, person.id, "jobs.lever.co", cookies)
    db_session.refresh(account)

    loaded = load_session_cookies(db_session, person.id, "jobs.lever.co")
    assert loaded == cookies
    assert account.last_login_at is not None


def test_manual_otp_store_and_resolve() -> None:
    store_manual_otp(42, "123456")
    assert peek_manual_otp(42) == "123456"
    assert resolve_otp("example.com", application_id=42) == "123456"
    assert pop_manual_otp(42) is None


def test_create_site_account_masks_password(db_session, person, fernet_key) -> None:
    result = create_site_account(
        db_session,
        SiteAccountCreate(
            person_id=person.id,
            platform="workday",
            domain="wd5.myworkdayjobs.com",
            username="user@corp.com",
            password="hunter2",
        ),
    )
    assert result.username == "user@corp.com"
    assert result.password_masked == "****"
    assert result.has_session is False


def test_list_site_accounts(db_session, person, fernet_key) -> None:
    create_site_account(
        db_session,
        SiteAccountCreate(
            person_id=person.id,
            platform="ashby",
            domain="jobs.ashbyhq.com",
            username="me@example.com",
            password="pass",
        ),
    )
    accounts = list_site_accounts(db_session, person_id=person.id)
    assert len(accounts) == 1
    assert accounts[0].password_masked == "****"


@pytest.mark.asyncio
async def test_try_login_fills_form() -> None:
    page = AsyncMock()
    username_el = AsyncMock()
    password_el = AsyncMock()
    submit_el = AsyncMock()
    password_visible = True

    async def query_selector(selector: str):
        nonlocal password_visible
        if "email" in selector:
            return username_el
        if "password" in selector:
            return password_el if password_visible else None
        if "submit" in selector or "Sign in" in selector:
            return submit_el
        return None

    async def click_side_effect():
        nonlocal password_visible
        password_visible = False

    submit_el.click = AsyncMock(side_effect=click_side_effect)
    page.query_selector = query_selector
    page.wait_for_timeout = AsyncMock()

    from seejob.services.auth import SiteCredentials

    creds = SiteCredentials(
        account_id=1,
        platform="test",
        domain="careers.example.com",
        username="user@test.com",
        password="secret",
    )
    success = await try_login(page, creds, domain="careers.example.com")
    assert success is True
    username_el.fill.assert_awaited_once_with("user@test.com")
    password_el.fill.assert_awaited_once_with("secret")


def test_site_accounts_api_crud(client, db_session, person, fernet_key) -> None:
    create_resp = client.post(
        "/api/v1/site-accounts",
        json={
            "person_id": person.id,
            "platform": "greenhouse",
            "domain": "boards.greenhouse.io",
            "username": "user@example.com",
            "password": "secret",
        },
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["password_masked"] == "****"
    account_id = data["id"]

    list_resp = client.get(f"/api/v1/site-accounts?person_id={person.id}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    get_resp = client.get(f"/api/v1/site-accounts/{account_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["username"] == "user@example.com"

    patch_resp = client.patch(
        f"/api/v1/site-accounts/{account_id}",
        json={"username": "new@example.com"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["username"] == "new@example.com"

    del_resp = client.delete(f"/api/v1/site-accounts/{account_id}")
    assert del_resp.status_code == 204


def test_provide_otp_endpoint(client, db_session, person, fernet_key) -> None:
    from seejob.models.application import Application, ApplicationStatus
    from seejob.models.job import Job, JobStatus

    job = Job(url="https://careers.example.com/apply", title="Dev", company="Co", source="test", status=JobStatus.NEW)
    db_session.add(job)
    db_session.flush()
    app = Application(person_id=person.id, job_id=job.id, status=ApplicationStatus.AUTH_REQUIRED)
    db_session.add(app)
    db_session.commit()

    bad = client.post(f"/api/v1/applications/{app.id}/provide-otp", json={"otp": "999888"})
    assert bad.status_code == 200
    assert peek_manual_otp(app.id) == "999888"

    wrong_status = client.post(
        f"/api/v1/applications/99999/provide-otp",
        json={"otp": "111"},
    )
    assert wrong_status.status_code == 404
