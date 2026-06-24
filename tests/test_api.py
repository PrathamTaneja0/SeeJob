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
