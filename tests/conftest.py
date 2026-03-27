from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

def _generate_key_pair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


DEFAULT_PRIVATE_KEY, DEFAULT_PUBLIC_KEY = _generate_key_pair()
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("JWT_ACCESS_PRIVATE_KEY", DEFAULT_PRIVATE_KEY)
os.environ.setdefault("JWT_ACCESS_PUBLIC_KEY", DEFAULT_PUBLIC_KEY)
os.environ.setdefault("JWT_ACCESS_KID", "auth-service-1")
os.environ.setdefault("JWT_ISSUER", "auth-service")
os.environ.setdefault("DB_NAME", "resource_db")
os.environ.setdefault("DB_USERNAME", "resource_user")
os.environ.setdefault("DB_PASSWORD", "resource_password")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "27017")
os.environ.setdefault("DB_ENGINE", "mongodb")
os.environ.setdefault("MONGODB_DBNAME", "resource_db")
os.environ.setdefault("VALKEY_ADDR", "localhost:6379")
os.environ.setdefault("VALKEY_USE_TLS", "false")
os.environ.setdefault("AUTH_ACCESS_COOKIE_NAME", "access_token")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from app.config import Settings, load_settings_from_env  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return load_settings_from_env()


@pytest.fixture
def app(settings: Settings):
    return create_app(
        settings=settings,
        load_prod_secrets_fn=lambda: None,
        connect_mongo_fn=lambda _: None,
        connect_valkey_fn=lambda _: None,
    )


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def make_token(settings: Settings):
    private_key = settings.auth.access_token_private_key

    def _issue(username: str = "alice", role: str = "user", expired: bool = False) -> str:
        now = datetime.now(tz=UTC)
        exp = now - timedelta(minutes=1) if expired else now + timedelta(minutes=15)
        payload = {
            "username": username,
            "role": role,
            "iss": settings.auth.issuer,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": settings.auth.access_token_key_id})

    return _issue
