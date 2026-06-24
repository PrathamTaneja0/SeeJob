"""API smoke tests."""

def test_health_check(client) -> None:
    """Health endpoint returns ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_create_and_get_profile(client) -> None:
    """Profile CRUD round-trip."""
    create_resp = client.post(
        "/api/v1/profiles",
        json={
            "full_name": "Test User",
            "email": "test@example.com",
            "work_authorization": "citizen",
        },
    )
    assert create_resp.status_code == 201
    person_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/v1/profiles/{person_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["email"] == "test@example.com"


def test_policy_defaults(client) -> None:
    """Policy endpoint returns safe defaults."""
    response = client.get("/api/v1/policy")
    assert response.status_code == 200
    data = response.json()
    assert data["require_doc_approval"] is True
    assert data["require_submit_approval"] is True
    assert data["auto_apply"] is False


def test_duplicate_email_returns_409(client) -> None:
    """Creating a profile with a duplicate email returns 409 Conflict."""
    payload = {
        "full_name": "Test User",
        "email": "dup@example.com",
        "work_authorization": "citizen",
    }
    first = client.post("/api/v1/profiles", json=payload)
    assert first.status_code == 201

    second = client.post("/api/v1/profiles", json=payload)
    assert second.status_code == 409
    assert "already registered" in second.json()["detail"]


def test_events_polling_endpoint(client) -> None:
    """Events API returns emitted orchestrator events."""
    from seejob.services.events import clear_events, emit_event

    clear_events()
    emit_event("test_event", "hello", worker_name="test")

    response = client.get("/api/v1/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[-1]["event_type"] == "test_event"
    assert data[-1]["message"] == "hello"

