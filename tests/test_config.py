from __future__ import annotations

import pytest

from app.config import load_settings_from_env, normalize_pem_env, parse_duration_seconds


def test_normalize_pem_env_handles_escaped_newlines():
    original = '"line1\\nline2"'
    assert normalize_pem_env(original) == "line1\nline2"


def test_parse_duration_seconds():
    assert parse_duration_seconds("15m") == 900
    assert parse_duration_seconds("2h") == 7200
    assert parse_duration_seconds("30s") == 30


@pytest.mark.parametrize("invalid", ["", "15", "x5m", "5d"])
def test_parse_duration_seconds_invalid(invalid: str):
    with pytest.raises(ValueError):
        parse_duration_seconds(invalid)


def test_load_settings_valkey_tls_defaults(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("VALKEY_USE_TLS", raising=False)
    dev_settings = load_settings_from_env()
    assert dev_settings.valkey.use_tls is False

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("VALKEY_USE_TLS", raising=False)
    prod_settings = load_settings_from_env()
    assert prod_settings.valkey.use_tls is True


def test_load_settings_requires_key(monkeypatch):
    monkeypatch.delenv("JWT_ACCESS_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("JWT_ACCESS_PUBLIC_KEY", raising=False)
    with pytest.raises(ValueError):
        load_settings_from_env()
