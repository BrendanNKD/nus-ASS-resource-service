from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from redis.exceptions import RedisError

from app.config import Settings


@dataclass(frozen=True)
class AuthClaims:
    username: str
    role: str


@dataclass(frozen=True)
class RefreshSession:
    session_id: str
    username: str
    role: str


def get_token_from_request(request: Request, cookie_name: str) -> str:
    cookie_value = request.cookies.get(cookie_name, "")
    if cookie_value:
        return cookie_value

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""


def unauthorized(error: str, code: str, action: str = "refresh") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": error, "code": code, "action": action},
        headers={"WWW-Authenticate": "Bearer"},
    )


def refresh_token_hash(raw_refresh_token: str) -> str:
    return hashlib.sha256(raw_refresh_token.encode("utf-8")).hexdigest()


def parse_valkey_json(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if not isinstance(payload, str):
        return None

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def check_refresh_session(
    valkey: Any,
    raw_refresh_token: str,
    prefix: str,
) -> RefreshSession | None:
    if not raw_refresh_token:
        return None

    token_hash = refresh_token_hash(raw_refresh_token)
    revoked_key = f"{prefix}:revoked:{token_hash}"
    token_key = f"{prefix}:token:{token_hash}"

    if valkey.exists(revoked_key):
        return None

    token_metadata = parse_valkey_json(valkey.get(token_key))
    if token_metadata is None:
        return None

    session_id = token_metadata.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None

    session = parse_valkey_json(valkey.get(f"{prefix}:session:{session_id}"))
    if session is None:
        return None

    if session.get("current_token_hash") != token_hash:
        return None

    return RefreshSession(
        session_id=session_id,
        username=str(token_metadata.get("username", "")),
        role=str(token_metadata.get("role", "")),
    )


def require_refresh_session(request: Request, settings: Settings) -> RefreshSession:
    raw_refresh_token = request.cookies.get(settings.auth.refresh_cookie_name, "")
    if not raw_refresh_token:
        raise unauthorized("Authentication session required", "AUTH_SESSION_MISSING")

    valkey = getattr(request.app.state, "valkey", None)
    if valkey is None:
        raise unauthorized("Authentication session unavailable", "AUTH_SESSION_UNAVAILABLE")

    try:
        session = check_refresh_session(valkey, raw_refresh_token, settings.valkey.prefix)
    except RedisError as exc:
        raise unauthorized(
            "Authentication session unavailable",
            "AUTH_SESSION_UNAVAILABLE",
        ) from exc

    if session is None:
        raise unauthorized("Authentication session invalid or expired", "AUTH_SESSION_INVALID")
    return session


def require_auth(request: Request) -> AuthClaims:
    settings: Settings = request.app.state.settings
    token = get_token_from_request(request, settings.auth.access_cookie_name)
    if not token:
        raise unauthorized("Authentication required", "AUTH_TOKEN_MISSING")

    session = require_refresh_session(request, settings)

    try:
        payload = jwt.decode(
            token,
            key=settings.auth.access_token_public_key,
            algorithms=["RS256"],
            issuer=settings.auth.issuer,
            options={"require": ["exp", "iat", "nbf"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise unauthorized("Access token expired", "AUTH_TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise unauthorized("Invalid access token", "AUTH_TOKEN_INVALID") from exc

    username = payload.get("username")
    role = payload.get("role")
    if not username or not role:
        raise unauthorized("Invalid access token", "AUTH_TOKEN_INVALID")

    if session.username and session.username != str(username):
        raise unauthorized("Authentication session invalid or expired", "AUTH_SESSION_INVALID")
    if session.role and session.role != str(role):
        raise unauthorized("Authentication session invalid or expired", "AUTH_SESSION_INVALID")

    return AuthClaims(username=str(username), role=str(role))


REQUIRE_AUTH_DEPENDENCY = Depends(require_auth)


def require_role(*allowed_roles: str):
    def dependency(claims: AuthClaims = REQUIRE_AUTH_DEPENDENCY) -> AuthClaims:
        if claims.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "Forbidden", "code": "AUTH_FORBIDDEN"},
            )
        return claims

    return dependency
