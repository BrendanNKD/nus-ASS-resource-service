from __future__ import annotations

import json

from app.secrets_loader import (
    SECRET_DATABASE,
    SECRET_JWT,
    SECRET_VALKEY,
    load_database_secret,
    load_prod_secrets,
    load_secret_map,
)


def test_load_secret_map_success():
    data = load_secret_map("prod/jwt", getter=lambda _: '{"A":"B"}')
    assert data == {"A": "B"}


def test_load_database_secret_success():
    secret = load_database_secret(
        getter=lambda _: json.dumps(
            {
                "username": "user",
                "password": "pass",
                "engine": "mongodb",
                "host": "localhost",
                "port": 27017,
                "dbname": "resource_db",
            }
        )
    )
    assert secret.username == "user"
    assert secret.port == "27017"


def test_load_prod_secrets_sets_expected_values():
    captured: dict[str, str] = {}

    def fake_getter(name: str) -> str:
        if name == SECRET_JWT:
            return '{"JWT_ACCESS_PUBLIC_KEY":"pub","JWT_ACCESS_PRIVATE_KEY":"priv"}'
        if name == SECRET_DATABASE:
            return json.dumps(
                {
                    "username": "u",
                    "password": "p",
                    "engine": "mongodb",
                    "host": "h",
                    "port": 27017,
                    "dbname": "d",
                }
            )
        if name == SECRET_VALKEY:
            return '{"VALKEY_ADDR":"localhost:6379"}'
        raise RuntimeError("unexpected secret")

    load_prod_secrets(
        getter=fake_getter, setter=lambda key, value: captured.__setitem__(key, value)
    )

    assert captured["JWT_ACCESS_PUBLIC_KEY"] == "pub"
    assert captured["DB_USERNAME"] == "u"
    assert captured["DB_PASSWORD"] == "p"
    assert captured["DB_NAME"] == "d"
    assert captured["MONGODB_DBNAME"] == "d"
    assert captured["VALKEY_ADDR"] == "localhost:6379"


def test_load_prod_secrets_tolerates_missing_valkey():
    captured: dict[str, str] = {}

    def fake_getter(name: str) -> str:
        if name == SECRET_JWT:
            return '{"JWT_ACCESS_PUBLIC_KEY":"pub","JWT_ACCESS_PRIVATE_KEY":"priv"}'
        if name == SECRET_DATABASE:
            return json.dumps(
                {
                    "username": "u",
                    "password": "p",
                    "engine": "mongodb",
                    "host": "h",
                    "port": 27017,
                    "dbname": "d",
                }
            )
        if name == SECRET_VALKEY:
            raise RuntimeError("missing")
        raise RuntimeError("unexpected secret")

    load_prod_secrets(
        getter=fake_getter, setter=lambda key, value: captured.__setitem__(key, value)
    )
    assert captured["DB_USERNAME"] == "u"
