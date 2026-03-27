from __future__ import annotations

import pytest
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from app.mongo_client import build_mongo_uri, connect_mongo
from app.valkey_client import connect_valkey, split_host_port


class FakeMongoClient:
    def __init__(self, *_args, **_kwargs):
        self.admin = self

    def command(self, _cmd: str):
        return {"ok": 1}


class FailingMongoClient:
    def __init__(self, *_args, **_kwargs):
        self.admin = self

    def command(self, _cmd: str):
        raise PyMongoError("boom")


class FakeValkeyClient:
    def __init__(self, *_args, **_kwargs):
        pass

    def ping(self):
        return True

    def close(self):
        return None


class FailingValkeyClient:
    def __init__(self, *_args, **_kwargs):
        pass

    def ping(self):
        raise RedisError("unreachable")

    def close(self):
        return None


def test_split_host_port():
    assert split_host_port("localhost") == ("localhost", 6379)
    assert split_host_port("cache.local:6380") == ("cache.local", 6380)


def test_build_mongo_uri_from_parts(settings):
    uri = build_mongo_uri(settings)
    assert uri.startswith("mongodb://")
    assert settings.db.name in uri


def test_connect_mongo_success(monkeypatch, settings):
    monkeypatch.setattr("app.mongo_client.MongoClient", FakeMongoClient)
    client = connect_mongo(settings)
    assert client is not None


def test_connect_mongo_failure_in_dev(monkeypatch, settings):
    monkeypatch.setattr("app.mongo_client.MongoClient", FailingMongoClient)
    client = connect_mongo(settings)
    assert client is None


def test_connect_valkey_success(monkeypatch, settings):
    monkeypatch.setattr("app.valkey_client.redis.Redis", FakeValkeyClient)
    client = connect_valkey(settings)
    assert client is not None


def test_connect_valkey_failure_in_dev(monkeypatch, settings):
    monkeypatch.setattr("app.valkey_client.redis.Redis", FailingValkeyClient)
    client = connect_valkey(settings)
    assert client is None


def test_connect_valkey_failure_in_prod(monkeypatch, settings):
    monkeypatch.setattr("app.valkey_client.redis.Redis", FailingValkeyClient)
    prod_settings = settings.__class__(
        app_env="prod",
        port=settings.port,
        db=settings.db,
        auth=settings.auth,
        cookie=settings.cookie,
        cors=settings.cors,
        valkey=settings.valkey,
    )

    with pytest.raises(RuntimeError):
        connect_valkey(prod_settings)
