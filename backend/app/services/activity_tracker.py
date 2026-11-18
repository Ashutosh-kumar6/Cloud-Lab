"""
Activity tracker — stores per-user last-activity timestamps in Redis.

Key layout:
    cloudlab:activity:<user_id>  →  Unix timestamp (float) stored as a plain string.
    cloudlab:active_users        →  Redis Set of user_id strings with active environments.

All helpers are intentionally thin wrappers around redis-py so that tests can
inject a fakeredis client easily.
"""
from __future__ import annotations

import logging
import time
from typing import Protocol

logger = logging.getLogger(__name__)

# Namespace prefix keeps our keys isolated from Celery broker keys.
_PREFIX = "cloudlab:activity:"
_ACTIVE_SET = "cloudlab:active_users"
# Expire the timestamp key automatically after 2× the maximum idle window so
# Redis doesn't accumulate stale keys indefinitely (the monitor cleans them
# up earlier, but this is a safety net).
_KEY_TTL_SECONDS = 7200  # 2 hours


class RedisClient(Protocol):
    """Minimal subset of redis.Redis used here (aids mocking in tests)."""

    def set(self, name: str, value: str, ex: int | None = None) -> None: ...
    def get(self, name: str) -> bytes | None: ...
    def sadd(self, name: str, *values: str) -> int: ...
    def srem(self, name: str, *values: str) -> int: ...
    def smembers(self, name: str) -> set[bytes]: ...
    def delete(self, *names: str) -> int: ...


def _key(user_id: int | str) -> str:
    return f"{_PREFIX}{user_id}"


def touch_user(redis: RedisClient, user_id: int) -> None:
    """Record *now* as the last activity for *user_id*."""
    now = str(time.time())
    redis.set(_key(user_id), now, ex=_KEY_TTL_SECONDS)
    redis.sadd(_ACTIVE_SET, str(user_id))
    logger.debug("Activity touched for user %s", user_id)


def get_idle_seconds(redis: RedisClient, user_id: int | str) -> float | None:
    """Return how many seconds ago the user was last active, or None if unknown."""
    raw = redis.get(_key(user_id))
    if raw is None:
        return None
    try:
        last_seen = float(raw)
        return time.time() - last_seen
    except (ValueError, TypeError):
        return None


def clear_user(redis: RedisClient, user_id: int | str) -> None:
    """Remove all activity tracking data for *user_id*."""
    redis.delete(_key(user_id))
    redis.srem(_ACTIVE_SET, str(user_id))


def all_active_user_ids(redis: RedisClient) -> list[str]:
    """Return all user IDs currently in the active set."""
    members = redis.smembers(_ACTIVE_SET)
    return [m.decode() if isinstance(m, bytes) else m for m in members]
