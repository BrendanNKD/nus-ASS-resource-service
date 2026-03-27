from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives import serialization


@dataclass(frozen=True)
class DatabaseConfig:
    engine: str
    host: str
    port: str
    name: str
    username: str
    password: str
    uri: str
    tls: bool


@dataclass(frozen=True)
class AuthConfig:
    access_token_private_key: Any | None
    access_token_public_key: Any
    access_token_key_id: str
    issuer: str
    access_token_ttl_seconds: int
    access_cookie_name: str


@dataclass(frozen=True)
class CookieConfig:
    domain: str
    secure: bool
    same_site: str
    path: str


@dataclass(frozen=True)
class CORSConfig:
    allowed_origins: list[str]


@dataclass(frozen=True)
class ValkeyConfig:
    addr: str
    password: str
    db: int
    prefix: str
    use_tls: bool


@dataclass(frozen=True)
class Settings:
    app_env: str
    port: str
    db: DatabaseConfig
    auth: AuthConfig
    cookie: CookieConfig
    cors: CORSConfig
    valkey: ValkeyConfig


def resolve_app_env() -> str:
    return os.getenv("APP_ENV", "dev").strip() or "dev"


def load_settings_from_env() -> Settings:
    app_env = resolve_app_env()

    private_key_pem = normalize_pem_env(os.getenv("JWT_ACCESS_PRIVATE_KEY", ""))
    public_key_pem = normalize_pem_env(os.getenv("JWT_ACCESS_PUBLIC_KEY", ""))

    if not private_key_pem and not public_key_pem:
        raise ValueError("Either JWT_ACCESS_PRIVATE_KEY or JWT_ACCESS_PUBLIC_KEY must be set")

    private_key = parse_private_key(private_key_pem) if private_key_pem else None
    public_key = parse_public_key(public_key_pem) if public_key_pem else None
    if public_key is None and private_key is not None:
        public_key = private_key.public_key()
    if public_key is None:
        raise ValueError("JWT public key could not be resolved")

    access_token_ttl_seconds = parse_duration_seconds(os.getenv("JWT_ACCESS_TTL", "15m"))

    db_name = os.getenv("MONGODB_DBNAME", os.getenv("DB_NAME", "")).strip()
    if not db_name:
        raise ValueError("DB_NAME or MONGODB_DBNAME must be set")

    db_username = os.getenv("MONGODB_USERNAME", os.getenv("DB_USERNAME", "")).strip()
    db_password = os.getenv("MONGODB_PASSWORD", os.getenv("DB_PASSWORD", "")).strip()
    db_host = os.getenv("MONGODB_HOST", os.getenv("DB_HOST", "localhost")).strip() or "localhost"
    db_port = os.getenv("MONGODB_PORT", os.getenv("DB_PORT", "27017")).strip() or "27017"
    db_uri = os.getenv("MONGODB_URI", "").strip()
    db_tls_raw = os.getenv("MONGODB_TLS", "").strip().lower()
    if db_tls_raw:
        db_tls = parse_bool(db_tls_raw, "MONGODB_TLS")
    else:
        db_tls = app_env == "prod"

    valkey_db = parse_int(os.getenv("VALKEY_DB", "0"), "VALKEY_DB")

    valkey_use_tls_raw = os.getenv("VALKEY_USE_TLS", "").strip().lower()
    if valkey_use_tls_raw:
        valkey_use_tls = parse_bool(valkey_use_tls_raw, "VALKEY_USE_TLS")
    else:
        valkey_use_tls = app_env == "prod"

    return Settings(
        app_env=app_env,
        port=os.getenv("APP_PORT", "8080"),
        db=DatabaseConfig(
            engine=os.getenv("DB_ENGINE", "mongodb"),
            host=db_host,
            port=db_port,
            name=db_name,
            username=db_username,
            password=db_password,
            uri=db_uri,
            tls=db_tls,
        ),
        auth=AuthConfig(
            access_token_private_key=private_key,
            access_token_public_key=public_key,
            access_token_key_id=os.getenv("JWT_ACCESS_KID", "auth-service-1"),
            issuer=os.getenv("JWT_ISSUER", "auth-service"),
            access_token_ttl_seconds=access_token_ttl_seconds,
            access_cookie_name=os.getenv("AUTH_ACCESS_COOKIE_NAME", "access_token"),
        ),
        cookie=CookieConfig(
            domain=os.getenv("COOKIE_DOMAIN", ""),
            secure=parse_bool(os.getenv("COOKIE_SECURE", str(app_env == "prod")), "COOKIE_SECURE"),
            same_site=os.getenv("COOKIE_SAMESITE", "lax").lower(),
            path=os.getenv("COOKIE_PATH", "/"),
        ),
        cors=CORSConfig(
            allowed_origins=parse_csv(os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")),
        ),
        valkey=ValkeyConfig(
            addr=os.getenv("VALKEY_ADDR", "localhost:6379"),
            password=os.getenv("VALKEY_PASSWORD", ""),
            db=valkey_db,
            prefix=os.getenv("VALKEY_PREFIX", "resource:cache"),
            use_tls=valkey_use_tls,
        ),
    )


def parse_int(value: str, key: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {key}: {value}") from exc


def parse_bool(value: str, key: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid {key}: {value}")


def parse_duration_seconds(value: str) -> int:
    unit = value[-1:]
    number = value[:-1]
    if not number:
        raise ValueError(f"Invalid duration: {value}")
    try:
        n = int(number)
    except ValueError as exc:
        raise ValueError(f"Invalid duration: {value}") from exc

    if unit == "s":
        return n
    if unit == "m":
        return n * 60
    if unit == "h":
        return n * 3600
    raise ValueError(f"Invalid duration: {value}")


def parse_private_key(pem_value: str) -> Any:
    try:
        return serialization.load_pem_private_key(pem_value.encode("utf-8"), password=None)
    except ValueError as exc:
        raise ValueError("Invalid JWT_ACCESS_PRIVATE_KEY") from exc


def parse_public_key(pem_value: str) -> Any:
    try:
        return serialization.load_pem_public_key(pem_value.encode("utf-8"))
    except ValueError as exc:
        raise ValueError("Invalid JWT_ACCESS_PUBLIC_KEY") from exc


def parse_csv(value: str) -> list[str]:
    return [entry.strip() for entry in value.split(",") if entry.strip()]


def normalize_pem_env(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    value = value.replace("\\r\\n", "\n").replace("\\n", "\n")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return value
