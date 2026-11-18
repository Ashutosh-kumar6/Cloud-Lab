from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import metrics
from app.runner.sandbox import RunResult


def test_metrics_endpoint_exposed(client: TestClient):
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "http_requests_total" in res.text or "python_gc_objects_collected_total" in res.text


def test_login_failure_increments_metric(client: TestClient):
    before = metrics.LOGIN_FAILURES._value.get()

    res = client.post(
        "/api/v1/auth/login",
        data={"username": "nonexistent@cloudlab.edu", "password": "wrongpassword"},
    )
    assert res.status_code == 401

    after = metrics.LOGIN_FAILURES._value.get()
    assert after == before + 1


def test_submission_passed_increments_graded_metric(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    # Create exercise
    ex_res = client.post(
        "/api/v1/admin/exercises",
        json={
            "title": "Metrics test exercise passed",
            "topic": "metrics",
            "difficulty": "easy",
            "description": "Calculate something",
            "test_cases": [{"input_text": "1", "expected_output": "1", "is_hidden": False}],
        },
        headers=auth_headers(teacher_token),
    )
    ex_id = ex_res.json()["id"]

    before_passed = metrics.SUBMISSIONS_GRADED.labels(status="passed")._value.get()

    with patch("app.runner.grader.run_python", return_value=RunResult("1", "", 0, False)):
        sub_res = client.post(
            "/api/v1/submissions",
            json={"exercise_id": ex_id, "code": "print(1)"},
            headers=auth_headers(student_token),
        )
        assert sub_res.status_code == 201

    after_passed = metrics.SUBMISSIONS_GRADED.labels(status="passed")._value.get()
    assert after_passed == before_passed + 1


def test_submission_failed_increments_failure_metrics(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    ex_res = client.post(
        "/api/v1/admin/exercises",
        json={
            "title": "Metrics test exercise failed",
            "topic": "metrics",
            "difficulty": "easy",
            "description": "Calculate something",
            "test_cases": [{"input_text": "1", "expected_output": "1", "is_hidden": False}],
        },
        headers=auth_headers(teacher_token),
    )
    ex_id = ex_res.json()["id"]

    before_graded = metrics.SUBMISSIONS_GRADED.labels(status="failed")._value.get()
    before_failures = metrics.SUBMISSION_FAILURES._value.get()

    with patch("app.runner.grader.run_python", return_value=RunResult("wrong", "", 0, False)):
        sub_res = client.post(
            "/api/v1/submissions",
            json={"exercise_id": ex_id, "code": "print(2)"},
            headers=auth_headers(student_token),
        )
        assert sub_res.status_code == 201

    after_graded = metrics.SUBMISSIONS_GRADED.labels(status="failed")._value.get()
    after_failures = metrics.SUBMISSION_FAILURES._value.get()

    assert after_graded == before_graded + 1
    assert after_failures == before_failures + 1


def test_submission_timeout_increments_timeout_and_failure_metrics(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    ex_res = client.post(
        "/api/v1/admin/exercises",
        json={
            "title": "Metrics test exercise timeout",
            "topic": "metrics",
            "difficulty": "easy",
            "description": "Calculate something",
            "test_cases": [{"input_text": "1", "expected_output": "1", "is_hidden": False}],
        },
        headers=auth_headers(teacher_token),
    )
    ex_id = ex_res.json()["id"]

    before_timeouts = metrics.SANDBOX_TIMEOUTS._value.get()
    before_failures = metrics.SUBMISSION_FAILURES._value.get()

    with patch("app.runner.grader.run_python", return_value=RunResult("", "", None, True)):
        sub_res = client.post(
            "/api/v1/submissions",
            json={"exercise_id": ex_id, "code": "while True: pass"},
            headers=auth_headers(student_token),
        )
        assert sub_res.status_code == 201

    after_timeouts = metrics.SANDBOX_TIMEOUTS._value.get()
    after_failures = metrics.SUBMISSION_FAILURES._value.get()

    assert after_timeouts == before_timeouts + 1
    assert after_failures == before_failures + 1


def test_metrics_output_contains_custom_metrics(client: TestClient):
    metrics.record_login_failure()
    metrics.record_sandbox_timeout()
    metrics.record_submission_failure()
    metrics.record_submission_graded("passed")

    res = client.get("/metrics")
    assert res.status_code == 200
    assert "login_failures_total" in res.text
    assert "sandbox_timeouts_total" in res.text
    assert "submission_failures_total" in res.text
    assert "submissions_graded_total" in res.text
