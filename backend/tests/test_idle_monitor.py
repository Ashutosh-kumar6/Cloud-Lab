"""
Tests for:
  - activity_tracker: touch_user, get_idle_seconds, clear_user, all_active_user_ids
  - idle_monitor: run_idle_check logic (timeout, still-active, missing timestamp, re-entry)
  - Integration: submissions + quiz attempt endpoints update activity timestamp
  - Scheduler: start/stop lifecycle (without real Redis)
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.services.activity_tracker import (
    all_active_user_ids,
    clear_user,
    get_idle_seconds,
    touch_user,
    _ACTIVE_SET,
    _key,
)
from app.services.idle_monitor import run_idle_check


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def redis():
    """In-process fakeredis server — no network needed."""
    return fakeredis.FakeRedis()


# ===========================================================================
# activity_tracker tests
# ===========================================================================

class TestTouchUser:
    def test_touch_records_timestamp(self, redis):
        touch_user(redis, 42)
        raw = redis.get(_key(42))
        assert raw is not None
        ts = float(raw)
        assert abs(ts - time.time()) < 2

    def test_touch_adds_to_active_set(self, redis):
        touch_user(redis, 7)
        members = {m.decode() if isinstance(m, bytes) else m for m in redis.smembers(_ACTIVE_SET)}
        assert "7" in members

    def test_multiple_users_in_active_set(self, redis):
        touch_user(redis, 1)
        touch_user(redis, 2)
        touch_user(redis, 3)
        ids = all_active_user_ids(redis)
        assert set(ids) == {"1", "2", "3"}

    def test_touch_overwrites_old_timestamp(self, redis):
        redis.set(_key(99), str(time.time() - 1000))
        touch_user(redis, 99)
        idle = get_idle_seconds(redis, 99)
        assert idle is not None and idle < 2


class TestGetIdleSeconds:
    def test_returns_none_for_unknown_user(self, redis):
        assert get_idle_seconds(redis, 9999) is None

    def test_returns_seconds_since_last_touch(self, redis):
        past = time.time() - 300
        redis.set(_key(5), str(past))
        idle = get_idle_seconds(redis, 5)
        assert idle is not None
        assert 298 < idle < 302

    def test_handles_corrupt_timestamp(self, redis):
        redis.set(_key(5), b"not-a-number")
        assert get_idle_seconds(redis, 5) is None


class TestClearUser:
    def test_clear_removes_key_and_set_member(self, redis):
        touch_user(redis, 10)
        clear_user(redis, 10)
        assert get_idle_seconds(redis, 10) is None
        ids = all_active_user_ids(redis)
        assert "10" not in ids

    def test_clear_is_idempotent(self, redis):
        clear_user(redis, 404)  # never existed — should not raise
        assert get_idle_seconds(redis, 404) is None


# ===========================================================================
# idle_monitor tests
# ===========================================================================

class TestRunIdleCheck:
    def _make_redis(self, users: dict[str, float]) -> fakeredis.FakeRedis:
        """Seed a fakeredis with {user_id: seconds_ago} mapping."""
        r = fakeredis.FakeRedis()
        for uid, seconds_ago in users.items():
            ts = time.time() - seconds_ago
            r.set(_key(uid), str(ts))
            r.sadd(_ACTIVE_SET, uid)
        return r

    def test_stops_idle_user(self):
        """A user idle 35 min should be stopped when timeout is 30 min."""
        r = self._make_redis({"42": 35 * 60})
        with patch("app.core.config.settings.idle_timeout_minutes", 30):
            with patch("app.services.idle_monitor._stop_user_environment") as mock_stop:
                result = run_idle_check(r)

        assert "42" in result["stopped"]
        mock_stop.assert_called_once_with("42")
        # User should be cleared from Redis
        assert get_idle_seconds(r, "42") is None
        assert "42" not in all_active_user_ids(r)

    def test_keeps_active_user(self):
        """A user idle only 5 min should not be stopped with 30 min timeout."""
        r = self._make_redis({"7": 5 * 60})
        with patch("app.core.config.settings.idle_timeout_minutes", 30):
            with patch("app.services.idle_monitor._stop_user_environment") as mock_stop:
                result = run_idle_check(r)

        assert "7" not in result["stopped"]
        mock_stop.assert_not_called()
        assert get_idle_seconds(r, "7") is not None  # still tracked

    def test_exactly_at_boundary_is_stopped(self):
        """A user idle exactly at the timeout boundary should be stopped."""
        r = self._make_redis({"55": 30 * 60})
        with patch("app.core.config.settings.idle_timeout_minutes", 30):
            with patch("app.services.idle_monitor._stop_user_environment"):
                result = run_idle_check(r)
        # idle >= timeout → should be stopped
        assert "55" in result["stopped"]

    def test_mixed_users(self):
        """Only users past the threshold are stopped."""
        r = self._make_redis({
            "1": 2 * 60,    # active  — 2 min idle
            "2": 45 * 60,   # idle    — 45 min idle
            "3": 10 * 60,   # active  — 10 min idle
            "4": 90 * 60,   # idle    — 90 min idle
        })
        with patch("app.core.config.settings.idle_timeout_minutes", 30):
            with patch("app.services.idle_monitor._stop_user_environment"):
                result = run_idle_check(r)

        assert set(result["stopped"]) == {"2", "4"}
        assert set(result["checked"]) == {"1", "2", "3", "4"}

    def test_user_in_set_without_key_is_evicted(self):
        """A user in active set but with no timestamp key → skipped (evicted)."""
        r = fakeredis.FakeRedis()
        r.sadd(_ACTIVE_SET, "orphan")

        with patch("app.core.config.settings.idle_timeout_minutes", 30):
            with patch("app.services.idle_monitor._stop_user_environment") as mock_stop:
                result = run_idle_check(r)

        assert "orphan" in result["skipped"]
        mock_stop.assert_not_called()
        assert "orphan" not in all_active_user_ids(r)

    def test_no_active_users(self):
        """An empty active set results in an empty check."""
        r = fakeredis.FakeRedis()
        result = run_idle_check(r)
        assert result == {"checked": [], "stopped": [], "skipped": []}

    def test_configurable_timeout(self):
        """Timeout is read from settings.idle_timeout_minutes at call time."""
        r = self._make_redis({"77": 10 * 60})  # 10 min idle
        # With 5-min timeout → should be stopped
        with patch("app.core.config.settings.idle_timeout_minutes", 5):
            with patch("app.services.idle_monitor._stop_user_environment"):
                result_5 = run_idle_check(r)

        # Re-seed since user was cleared
        r = self._make_redis({"77": 10 * 60})
        # With 60-min timeout → should NOT be stopped
        with patch("app.core.config.settings.idle_timeout_minutes", 60):
            with patch("app.services.idle_monitor._stop_user_environment") as mock_stop:
                result_60 = run_idle_check(r)

        assert "77" in result_5["stopped"]
        assert "77" not in result_60["stopped"]
        mock_stop.assert_not_called()


# ===========================================================================
# Integration: API endpoints update activity tracker
# ===========================================================================

class TestSubmissionTouchesActivity:
    def test_submit_code_calls_touch_user(
        self,
        client: TestClient,
        teacher_token: str,
        student_token: str,
        auth_headers,
    ):
        # Create exercise
        ex_res = client.post(
            "/api/v1/admin/exercises",
            json={
                "title": "Touch test exercise",
                "topic": "basics",
                "difficulty": "easy",
                "description": "Test activity tracking",
                "test_cases": [{"input_text": "", "expected_output": "1", "is_hidden": False}],
            },
            headers=auth_headers(teacher_token),
        )
        ex_id = ex_res.json()["id"]

        from unittest.mock import patch as _patch
        from app.runner.sandbox import RunResult

        touched_users = []

        def fake_touch(redis_client, user_id):
            touched_users.append(user_id)

        with _patch("app.api.v1.submissions.touch_user", side_effect=fake_touch):
            with _patch("app.api.v1.submissions._get_redis", return_value=MagicMock()):
                with _patch(
                    "app.runner.grader.run_python",
                    return_value=RunResult("1", "", 0, False),
                ):
                    res = client.post(
                        "/api/v1/submissions",
                        json={"exercise_id": ex_id, "code": "print(1)"},
                        headers=auth_headers(student_token),
                    )

        assert res.status_code == 201
        # touch_user must have been called for the student
        assert len(touched_users) == 1


class TestQuizAttemptTouchesActivity:
    def test_start_and_submit_quiz_attempt_call_touch(
        self,
        client: TestClient,
        teacher_token: str,
        student_token: str,
        auth_headers,
    ):
        # Create quiz
        quiz_res = client.post(
            "/api/v1/quizzes",
            json={
                "title": "Activity quiz",
                "topic": "basics",
                "questions": [
                    {
                        "question_text": "2+2?",
                        "options": ["3", "4", "5", "6"],
                        "correct_option": 1,
                    }
                ],
            },
            headers=auth_headers(teacher_token),
        )
        quiz_id = quiz_res.json()["id"]
        q_id = quiz_res.json()["questions"][0]["id"]

        touched_users = []

        def fake_touch(redis_client, user_id):
            touched_users.append(user_id)

        with patch("app.api.v1.quizzes.touch_user", side_effect=fake_touch):
            with patch("app.api.v1.quizzes._get_redis", return_value=MagicMock()):
                start_res = client.post(
                    f"/api/v1/quizzes/{quiz_id}/attempts",
                    headers=auth_headers(student_token),
                )
                assert start_res.status_code == 201
                attempt_id = start_res.json()["attempt_id"]

                submit_res = client.post(
                    f"/api/v1/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
                    json={"answers": [{"question_id": q_id, "selected_option": 1}]},
                    headers=auth_headers(student_token),
                )
                assert submit_res.status_code == 200

        # touch_user called once for start, once for submit
        assert len(touched_users) == 2


# ===========================================================================
# Scheduler lifecycle
# ===========================================================================

class TestSchedulerLifecycle:
    def test_start_and_stop_scheduler(self):
        from app.core import scheduler as sched_module
        # Ensure clean state
        sched_module._scheduler = None

        sched_module.start_scheduler()
        assert sched_module._scheduler is not None
        assert sched_module._scheduler.running

        sched_module.stop_scheduler()
        assert sched_module._scheduler is None

    def test_start_scheduler_is_idempotent(self):
        from app.core import scheduler as sched_module
        sched_module._scheduler = None

        sched_module.start_scheduler()
        first = sched_module._scheduler

        sched_module.start_scheduler()  # second call — should reuse
        second = sched_module._scheduler

        assert first is second
        sched_module.stop_scheduler()

    def test_stop_scheduler_when_not_started(self):
        from app.core import scheduler as sched_module
        sched_module._scheduler = None
        sched_module.stop_scheduler()  # should not raise
        assert sched_module._scheduler is None
