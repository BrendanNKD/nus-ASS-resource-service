from __future__ import annotations


def test_missing_cookie_returns_refresh_hint(client):
    response = client.get("/api/v1/resources")
    assert response.status_code == 401
    assert response.json() == {
        "error": "Authentication required",
        "code": "AUTH_TOKEN_MISSING",
        "action": "refresh",
    }


def test_invalid_cookie_returns_refresh_hint(client, make_refresh_session):
    refresh_token = make_refresh_session()
    response = client.get(
        "/api/v1/resources",
        cookies={"access_token": "invalid.jwt.token", "refresh_token": refresh_token},
    )
    assert response.status_code == 401
    assert response.json() == {
        "error": "Invalid access token",
        "code": "AUTH_TOKEN_INVALID",
        "action": "refresh",
    }


def test_expired_cookie_returns_refresh_hint(client, make_auth_cookies):
    response = client.get("/api/v1/resources", cookies=make_auth_cookies(expired=True))
    assert response.status_code == 401
    assert response.json() == {
        "error": "Access token expired",
        "code": "AUTH_TOKEN_EXPIRED",
        "action": "refresh",
    }


def test_missing_refresh_cookie_returns_refresh_hint(client, make_token):
    token = make_token(username="alice", role="user")
    response = client.get("/api/v1/resources", cookies={"access_token": token})
    assert response.status_code == 401
    assert response.json() == {
        "error": "Authentication session required",
        "code": "AUTH_SESSION_MISSING",
        "action": "refresh",
    }


def test_missing_valkey_session_returns_refresh_hint(client, make_token):
    token = make_token(username="alice", role="user")
    response = client.get(
        "/api/v1/resources",
        cookies={"access_token": token, "refresh_token": "expired-refresh-token"},
    )
    assert response.status_code == 401
    assert response.json() == {
        "error": "Authentication session invalid or expired",
        "code": "AUTH_SESSION_INVALID",
        "action": "refresh",
    }


def test_revoked_valkey_session_returns_refresh_hint(client, make_token, make_refresh_session):
    token = make_token(username="alice", role="user")
    refresh_token = make_refresh_session(username="alice", role="user", revoked=True)
    response = client.get(
        "/api/v1/resources",
        cookies={"access_token": token, "refresh_token": refresh_token},
    )
    assert response.status_code == 401
    assert response.json() == {
        "error": "Authentication session invalid or expired",
        "code": "AUTH_SESSION_INVALID",
        "action": "refresh",
    }


def test_mismatched_valkey_session_returns_refresh_hint(
    client,
    make_token,
    make_refresh_session,
):
    token = make_token(username="alice", role="user")
    refresh_token = make_refresh_session(
        username="alice",
        role="user",
        session_overrides={"current_token_hash": "other-token-hash"},
    )
    response = client.get(
        "/api/v1/resources",
        cookies={"access_token": token, "refresh_token": refresh_token},
    )
    assert response.status_code == 401
    assert response.json() == {
        "error": "Authentication session invalid or expired",
        "code": "AUTH_SESSION_INVALID",
        "action": "refresh",
    }


def test_valkey_unavailable_fails_closed(client, make_auth_cookies):
    client.app.state.valkey = None
    response = client.get("/api/v1/resources", cookies=make_auth_cookies())
    assert response.status_code == 401
    assert response.json() == {
        "error": "Authentication session unavailable",
        "code": "AUTH_SESSION_UNAVAILABLE",
        "action": "refresh",
    }


def test_list_resources_with_valid_cookie(client, make_auth_cookies):
    response = client.get(
        "/api/v1/resources",
        cookies=make_auth_cookies(username="alice", role="user"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Resources fetched"
    assert payload["requested_by"] == "alice"
    assert payload["items"] == []


def test_create_resource_requires_admin(client, make_auth_cookies):
    response = client.post(
        "/api/v1/resources",
        cookies=make_auth_cookies(username="alice", role="user"),
        json={"resourceCode": "R1", "name": "Clinic A", "type": "clinic"},
    )
    assert response.status_code == 403
    assert response.json() == {"error": "Forbidden", "code": "AUTH_FORBIDDEN"}


def test_create_and_patch_resource_as_admin(client, make_auth_cookies):
    admin_cookies = make_auth_cookies(username="admin", role="admin")

    create_response = client.post(
        "/api/v1/resources",
        cookies=admin_cookies,
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
        cookies=admin_cookies,
        json={"resourceCode": "R1", "name": "Clinic A", "type": "clinic"},
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {
        "error": "Resource already exists",
        "code": "RESOURCE_CONFLICT",
    }

    patch_response = client.patch(
        "/api/v1/resources/R1/status",
        cookies=admin_cookies,
        json={"status": "maintenance"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["item"]["status"] == "maintenance"


def test_patch_resource_partial_update_as_admin(client, make_auth_cookies):
    admin_cookies = make_auth_cookies(username="admin", role="admin")

    create_response = client.post(
        "/api/v1/resources",
        cookies=admin_cookies,
        json={
            "resourceCode": "R2",
            "name": "Clinic A",
            "type": "clinic",
            "location": {
                "site": "NUS",
                "building": "University Health Centre",
                "floor": "1",
                "room": "A101",
                "timezone": "Asia/Singapore",
            },
            "slotDurationMin": 30,
            "defaultCapacity": 2,
            "tags": ["room", "clinic"],
            "metadata": {"source": "test"},
        },
    )
    assert create_response.status_code == 201

    patch_response = client.patch(
        "/api/v1/resources/R2",
        cookies=admin_cookies,
        json={"defaultCapacity": 4, "location": {"room": "A102"}},
    )

    assert patch_response.status_code == 200
    payload = patch_response.json()
    assert payload["message"] == "Resource updated"
    assert payload["item"]["resourceCode"] == "R2"
    assert payload["item"]["name"] == "Clinic A"
    assert payload["item"]["type"] == "clinic"
    assert payload["item"]["slotDurationMin"] == 30
    assert payload["item"]["defaultCapacity"] == 4
    assert payload["item"]["location"] == {
        "site": "NUS",
        "building": "University Health Centre",
        "floor": "1",
        "room": "A102",
        "timezone": "Asia/Singapore",
    }
    assert payload["item"]["tags"] == ["room", "clinic"]
    assert payload["item"]["metadata"] == {"source": "test"}


def test_patch_resource_requires_admin(client, make_auth_cookies):
    response = client.patch(
        "/api/v1/resources/R2",
        cookies=make_auth_cookies(username="alice", role="user"),
        json={"defaultCapacity": 4},
    )

    assert response.status_code == 403
    assert response.json() == {"error": "Forbidden", "code": "AUTH_FORBIDDEN"}


def test_patch_resource_rejects_resource_code_update(client, make_auth_cookies):
    response = client.patch(
        "/api/v1/resources/R2",
        cookies=make_auth_cookies(username="admin", role="admin"),
        json={"resourceCode": "R3"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert (
        payload["error"] == "Invalid request payload: resourceCode: Extra inputs are not permitted"
    )
    assert {
        "loc": ["resourceCode"],
        "message": "Extra inputs are not permitted",
        "type": "extra_forbidden",
    } in payload["details"]


def test_patch_resource_invalid_capacity_returns_validation_details(client, make_auth_cookies):
    response = client.patch(
        "/api/v1/resources/R2",
        cookies=make_auth_cookies(username="admin", role="admin"),
        json={"defaultCapacity": 0},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == (
        "Invalid request payload: defaultCapacity: Input should be greater than or equal to 1"
    )
    assert {
        "loc": ["defaultCapacity"],
        "message": "Input should be greater than or equal to 1",
        "type": "greater_than_equal",
    } in payload["details"]


def test_create_resource_invalid_payload_returns_validation_details(client, make_auth_cookies):
    response = client.post(
        "/api/v1/resources",
        cookies=make_auth_cookies(username="admin", role="admin"),
        json={"resourceCode": "", "name": "Clinic A", "type": "clinic", "slotDurationMin": 1},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == (
        "Invalid request payload: resourceCode: String should have at least 1 character; "
        "slotDurationMin: Input should be greater than or equal to 5"
    )
    assert {
        "loc": ["resourceCode"],
        "message": "String should have at least 1 character",
        "type": "string_too_short",
    } in payload["details"]
    assert {
        "loc": ["slotDurationMin"],
        "message": "Input should be greater than or equal to 5",
        "type": "greater_than_equal",
    } in payload["details"]


def test_patch_unknown_resource_returns_404(client, make_auth_cookies):
    response = client.patch(
        "/api/v1/resources/unknown/status",
        cookies=make_auth_cookies(username="admin", role="admin"),
        json={"status": "inactive"},
    )
    assert response.status_code == 404
    assert response.json() == {"error": "Resource not found", "code": "RESOURCE_NOT_FOUND"}


def test_patch_unknown_resource_fields_returns_404(client, make_auth_cookies):
    response = client.patch(
        "/api/v1/resources/unknown",
        cookies=make_auth_cookies(username="admin", role="admin"),
        json={"defaultCapacity": 4},
    )

    assert response.status_code == 404
    assert response.json() == {"error": "Resource not found", "code": "RESOURCE_NOT_FOUND"}


def test_auth_context_endpoint(client, make_auth_cookies):
    response = client.get(
        "/api/v1/auth/context",
        cookies=make_auth_cookies(username="bob", role="user"),
    )
    assert response.status_code == 200
    assert response.json() == {
        "message": "Authenticated",
        "user": {"username": "bob", "role": "user"},
    }
