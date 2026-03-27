from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request, status

from app.config import Settings


@dataclass(frozen=True)
class AuthClaims:
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


def require_auth(request: Request) -> AuthClaims:
    settings: Settings = request.app.state.settings
    token = get_token_from_request(request, settings.auth.access_cookie_name)
    if not token:
        raise unauthorized("Authentication required", "AUTH_TOKEN_MISSING")

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

    return AuthClaims(username=str(username), role=str(role))


def require_role(*allowed_roles: str):
    def dependency(claims: AuthClaims = Depends(require_auth)) -> AuthClaims:
        if claims.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "Forbidden", "code": "AUTH_FORBIDDEN"},
            )
        return claims

    return dependency
