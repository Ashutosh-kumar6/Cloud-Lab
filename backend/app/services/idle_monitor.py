"""
Idle monitor — the job that runs every minute and cleans up idle environments.

Design decisions
----------------
* "Environment" in this project is a per-user ephemeral Docker container
  created on-demand by sandbox.py and destroyed immediately after each
  grading run.  There is therefore nothing persistent to "stop"; the cleanup
  action here is to:
    1. Remove the user from the active-users Redis set so they are no longer
       tracked (their next submission will re-register them).
    2. Optionally kill any lingering Docker containers labelled with that
       user's ID (defensive cleanup; the sandbox already does force-remove).
* This keeps the monitor self-contained and testable without a live database.
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.services.activity_tracker import all_active_user_ids, clear_user, get_idle_seconds

logger = logging.getLogger(__name__)


def _stop_user_environment(user_id: str) -> None:
    """
    Stop and clean up the execution environment for *user_id*.

    In the current architecture the sandbox container is ephemeral (created +
    destroyed per grading run), so there is no long-lived container to kill.
    We log the action, remove the user from the activity tracker, and
    defensively attempt to stop any Docker containers with a matching label.
    """
    logger.info(
        "idle_monitor: stopping environment for user %s (idle > %d min)",
        user_id,
        settings.idle_timeout_minutes,
    )
    # Defensive: try to kill any stray containers bearing the user label.
    # We import here to avoid a hard failure when Docker is unavailable
    # (e.g. during unit tests).
    try:
        import docker
        from docker.errors import DockerException, NotFound

        client = docker.from_env()
        containers = client.containers.list(
            filters={"label": f"cloudlab_user={user_id}", "status": "running"}
        )
        for container in containers:
            try:
                container.stop(timeout=5)
                container.remove(force=True)
                logger.info(
                    "idle_monitor: removed container %s for user %s",
                    container.short_id,
                    user_id,
                )
            except (NotFound, DockerException) as exc:
                logger.warning(
                    "idle_monitor: could not remove container %s: %s",
                    container.short_id,
                    exc,
                )
    except Exception as exc:  # docker not installed / daemon unavailable
        logger.debug("idle_monitor: Docker cleanup skipped for user %s: %s", user_id, exc)


def run_idle_check(redis_client) -> dict[str, list[str]]:
    """
    Scan all active users, stop environments idle longer than the configured
    threshold, and return a summary dict for observability / testing.

    Returns:
        {
            "checked":  [<user_id>, ...],
            "stopped":  [<user_id>, ...],
            "skipped":  [<user_id>, ...],  # idle time unknown
        }
    """
    timeout_seconds = settings.idle_timeout_minutes * 60
    user_ids = all_active_user_ids(redis_client)

    checked: list[str] = []
    stopped: list[str] = []
    skipped: list[str] = []

    for uid in user_ids:
        checked.append(uid)
        idle = get_idle_seconds(redis_client, uid)

        if idle is None:
            # No timestamp recorded — treat as unknown, clean up defensively.
            logger.warning(
                "idle_monitor: user %s is in active set but has no timestamp; evicting",
                uid,
            )
            clear_user(redis_client, uid)
            skipped.append(uid)
            continue

        if idle >= timeout_seconds:
            _stop_user_environment(uid)
            clear_user(redis_client, uid)
            stopped.append(uid)
        else:
            logger.debug(
                "idle_monitor: user %s idle %.1fs / %ds — still active",
                uid,
                idle,
                timeout_seconds,
            )

    if stopped:
        logger.info("idle_monitor: stopped %d environment(s): %s", len(stopped), stopped)
    else:
        logger.debug("idle_monitor: tick complete, no environments stopped")

    return {"checked": checked, "stopped": stopped, "skipped": skipped}
