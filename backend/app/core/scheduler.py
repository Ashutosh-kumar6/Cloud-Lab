"""
APScheduler wrapper.

Provides a single BackgroundScheduler that:
- Is started in the FastAPI lifespan (skipped in testing mode).
- Runs the idle-environment monitor every minute.
- Uses a Redis client shared from the app's connection pool.
"""
from __future__ import annotations

import logging
import os

import redis as redis_module
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.services.idle_monitor import run_idle_check

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _make_redis_client() -> redis_module.Redis:
    return redis_module.from_url(settings.redis_url, decode_responses=False)


def _idle_check_job() -> None:
    """The callable that APScheduler invokes every minute."""
    try:
        client = _make_redis_client()
        result = run_idle_check(client)
        if result["stopped"]:
            logger.info("scheduler: idle check stopped users %s", result["stopped"])
    except Exception:
        logger.exception("scheduler: idle check job raised an exception")


def start_scheduler() -> None:
    """Create and start the background scheduler.  Idempotent."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _idle_check_job,
        trigger="interval",
        minutes=1,
        id="idle_monitor",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "scheduler: started idle monitor (timeout=%d min)",
        settings.idle_timeout_minutes,
    )


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully on app shutdown."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler: stopped")
    _scheduler = None
