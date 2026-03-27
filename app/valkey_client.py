from __future__ import annotations

import logging
import os

import redis

from app.config import Settings


logger = logging.getLogger(__name__)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def split_host_port(addr: str) -> tuple[str, int]:
    if ":" not in addr:
        return addr, 6379
    host, raw_port = addr.rsplit(":", 1)
    return host, int(raw_port)


def connect_valkey(settings: Settings) -> redis.Redis | None:
    host, port = split_host_port(settings.valkey.addr)
    use_tls = settings.valkey.use_tls

    if host in LOCAL_HOSTS and settings.app_env != "prod" and "VALKEY_USE_TLS" not in os.environ:
        use_tls = False

    client = redis.Redis(
        host=host,
        port=port,
        db=settings.valkey.db,
        password=settings.valkey.password or None,
        ssl=use_tls,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )

    try:
        client.ping()
    except redis.RedisError as exc:
        if settings.app_env == "prod":
            raise RuntimeError(f"Unable to connect to Valkey at {settings.valkey.addr}") from exc
        logger.warning("Valkey not reachable (%s): %s", settings.valkey.addr, exc)
        return None

    logger.info("Connected to Valkey at %s (tls=%s)", settings.valkey.addr, use_tls)
    return client


def close_valkey(client: redis.Redis | None) -> None:
    if client is None:
        return
    try:
        client.close()
    except Exception:  # noqa: BLE001
        logger.warning("Failed to close Valkey client cleanly")
