from __future__ import annotations

import logging
from urllib.parse import quote_plus

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.config import Settings


logger = logging.getLogger(__name__)


def build_mongo_uri(settings: Settings) -> str:
    if settings.db.uri:
        return settings.db.uri

    auth_prefix = ""
    if settings.db.username:
        username = quote_plus(settings.db.username)
        password = quote_plus(settings.db.password)
        auth_prefix = f"{username}:{password}@"

    return f"mongodb://{auth_prefix}{settings.db.host}:{settings.db.port}/{settings.db.name}"


def connect_mongo(settings: Settings) -> MongoClient | None:
    uri = build_mongo_uri(settings)
    kwargs = {"serverSelectionTimeoutMS": 3000}

    # Only force TLS when URI does not already declare transport settings.
    if settings.db.uri == "":
        kwargs["tls"] = settings.db.tls

    try:
        client = MongoClient(uri, **kwargs)
        client.admin.command("ping")
        logger.info("Connected to MongoDB")
        return client
    except PyMongoError as exc:
        if settings.app_env == "prod":
            raise RuntimeError("Unable to connect to MongoDB") from exc
        logger.warning("MongoDB not reachable: %s", exc)
        return None


def close_mongo(client: MongoClient | None) -> None:
    if client is None:
        return
    client.close()
