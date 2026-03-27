from __future__ import annotations


def test_missing_cookie_returns_refresh_hint(client):
    response = client.get("/api/v1/resources")
    assert response.status_code == 401
    assert response.json() == {
        "error": "Authentication required",
        "code": "AUTH_TOKEN_MISSING",
        "action": "refresh",
    }


def test_invalid_cookie_returns_refresh_hint(client):
    response = client.get("/api/v1/resources", cookies={"access_token": "invalid.jwt.token"})
    assert response.status_code == 401
    assert response.json() == {
        "error": "Invalid access token",
        "code": "AUTH_TOKEN_INVALID",
        "action": "refresh",
    }


def test_expired_cookie_returns_refresh_hint(client, make_token):
    expired = make_token(expired=True)
    response = client.get("/api/v1/resources", cookies={"access_token": expired})
    assert response.status_code == 401
    assert response.json() == {
        "error": "Access token expired",
        "code": "AUTH_TOKEN_EXPIRED",
        "action": "refresh",
    }


def test_list_resources_with_valid_cookie(client, make_token):
    token = make_token(username="alice", role="user")
    response = client.get("/api/v1/resources", cookies={"access_token": token})
    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Resources fetched"
    assert payload["requested_by"] == "alice"
    assert payload["items"] == []


def test_create_resource_requires_admin(client, make_token):
    token = make_token(username="alice", role="user")
    response = client.post(
        "/api/v1/resources",
        cookies={"access_token": token},
        json={"resourceCode": "R1", "name": "Clinic A", "type": "clinic"},
    )
    assert response.status_code == 403
    assert response.json() == {"error": "Forbidden", "code": "AUTH_FORBIDDEN"}


def test_create_and_patch_resource_as_admin(client, make_token):
    admin_token = make_token(username="admin", role="admin")

    create_response = client.post(
        "/api/v1/resources",
        cookies={"access_token": admin_token},
        json={
            "resourceCode": "R1",
            "name": "Clinic A",
            "type": "clinic",
            "slotDurationMin": 30,
            "defaultCapacity": 2,
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["item"]["resourceCode"] == "R1"

    duplicate_response = client.post(
        "/api/v1/resources",
        cookies={"access_token": admin_token},
        json={"resourceCode": "R1", "name": "Clinic A", "type": "clinic"},
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {"error": "Resource already exists", "code": "RESOURCE_CONFLICT"}

    patch_response = client.patch(
        "/api/v1/resources/R1/status",
        cookies={"access_token": admin_token},
        json={"status": "maintenance"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["item"]["status"] == "maintenance"


def test_patch_unknown_resource_returns_404(client, make_token):
    admin_token = make_token(username="admin", role="admin")
    response = client.patch(
        "/api/v1/resources/unknown/status",
        cookies={"access_token": admin_token},
        json={"status": "inactive"},
    )
    assert response.status_code == 404
    assert response.json() == {"error": "Resource not found", "code": "RESOURCE_NOT_FOUND"}


def test_auth_context_endpoint(client, make_token):
    token = make_token(username="bob", role="user")
    response = client.get("/api/v1/auth/context", cookies={"access_token": token})
    assert response.status_code == 200
    assert response.json() == {
        "message": "Authenticated",
        "user": {"username": "bob", "role": "user"},
    }
