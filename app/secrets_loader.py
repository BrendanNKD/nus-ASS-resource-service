from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Callable

import boto3
from botocore.exceptions import BotoCoreError, ClientError


logger = logging.getLogger(__name__)

SECRET_JWT = "prod/jwt"
# Keep the original secret name requested by the team, even though
# resource-service now uses MongoDB.
SECRET_DATABASE = "prod/postgres"
SECRET_POSTGRES = SECRET_DATABASE
SECRET_VALKEY = "prod/valkey"


@dataclass(frozen=True)
class DatabaseSecret:
    username: str
    password: str
    engine: str
    host: str
    port: str
    dbname: str
    uri: str


def get_secret(secret_name: str, region_name: str | None = None) -> str:
    client = boto3.client("secretsmanager", region_name=region_name)
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"Unable to load secret {secret_name}") from exc

    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError(f"Secret {secret_name} has no SecretString")
    return secret_string


def load_secret_map(secret_name: str, getter: Callable[[str], str] = get_secret) -> dict[str, str]:
    payload = getter(secret_name)
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError(f"Secret {secret_name} must be a JSON object")
    return {str(k): str(v) for k, v in parsed.items()}


def load_database_secret(secret_name: str = SECRET_DATABASE, getter: Callable[[str], str] = get_secret) -> DatabaseSecret:
    payload = getter(secret_name)
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Database secret must be a JSON object")

    username = str(parsed.get("username", parsed.get("MONGODB_USERNAME", "")))
    password = str(parsed.get("password", parsed.get("MONGODB_PASSWORD", "")))
    engine = str(parsed.get("engine", "mongodb"))
    host = str(parsed.get("host", parsed.get("MONGODB_HOST", "")))
    port = str(parsed.get("port", parsed.get("MONGODB_PORT", "")))
    dbname = str(parsed.get("dbname", parsed.get("database", parsed.get("MONGODB_DBNAME", ""))))
    uri = str(parsed.get("uri", parsed.get("MONGODB_URI", "")))

    if not dbname:
        raise ValueError("Database secret missing required field: dbname")

    if not uri:
        if not host:
            raise ValueError("Database secret missing required field: host")
        if not port.isdigit() or int(port) <= 0:
            raise ValueError(f"Database secret has invalid port: {port}")
    elif not port:
        # keep compatibility for clients that expect DB_PORT
        port = "27017"

    return DatabaseSecret(
        username=username,
        password=password,
        engine=engine,
        host=host,
        port=port,
        dbname=dbname,
        uri=uri,
    )


def set_env_from_map(values: dict[str, str], setter: Callable[[str, str], None] | None = None) -> None:
    set_env = setter or (lambda key, value: os.environ.__setitem__(key, value))
    for key, value in values.items():
        set_env(key, value)


def load_prod_secrets(
    getter: Callable[[str], str] = get_secret,
    setter: Callable[[str, str], None] | None = None,
) -> None:
    jwt_map = load_secret_map(SECRET_JWT, getter=getter)
    set_env_from_map(jwt_map, setter=setter)

    db = load_database_secret(secret_name=SECRET_DATABASE, getter=getter)
    db_env = {
        "DB_USERNAME": db.username,
        "DB_PASSWORD": db.password,
        "DB_ENGINE": db.engine,
        "DB_HOST": db.host,
        "DB_PORT": db.port,
        "DB_NAME": db.dbname,
        "MONGODB_USERNAME": db.username,
        "MONGODB_PASSWORD": db.password,
        "MONGODB_HOST": db.host,
        "MONGODB_PORT": db.port,
        "MONGODB_DBNAME": db.dbname,
    }
    if db.uri:
        db_env["MONGODB_URI"] = db.uri
    set_env_from_map(db_env, setter=setter)

    try:
        valkey_map = load_secret_map(SECRET_VALKEY, getter=getter)
        set_env_from_map(valkey_map, setter=setter)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Valkey secret %s not loaded: %s", SECRET_VALKEY, exc)
