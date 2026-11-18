from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.rate_limit import reset_rate_limits
from app.runner.sandbox import RunResult


def _create_exercise_with_tests(client: TestClient, teacher_token: str, auth_headers) -> int:
    res = client.post(
        "/api/v1/admin/exercises",
        json={
            "title": "Square of a number",
            "topic": "math",
            "difficulty": "easy",
            "description": "Read n and print n*n",
            "test_cases": [
                {"input_text": "4", "expected_output": "16", "is_hidden": False},
                {"input_text": "5", "expected_output": "25", "is_hidden": True},
            ],
        },
        headers=auth_headers(teacher_token),
    )
    return res.json()["id"]


def test_submission_correct_code_passes(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    ex_id = _create_exercise_with_tests(client, teacher_token, auth_headers)

    # Mock run_python returning correct output for each test case
    def fake_run(code: str, input_text: str) -> RunResult:
        n = int(input_text.strip())
        return RunResult(stdout=str(n * n), stderr="", exit_code=0, timed_out=False)

    with patch("app.runner.grader.run_python", side_effect=fake_run):
        res = client.post(
            "/api/v1/submissions",
            json={"exercise_id": ex_id, "code": "n = int(input())\nprint(n * n)"},
            headers=auth_headers(student_token),
        )

    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "passed"
    assert data["passed_count"] == 2
    assert data["total_count"] == 2


def test_submission_wrong_code_fails(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    ex_id = _create_exercise_with_tests(client, teacher_token, auth_headers)

    # Mock run_python returning wrong output
    def fake_run(code: str, input_text: str) -> RunResult:
        return RunResult(stdout="0", stderr="", exit_code=0, timed_out=False)

    with patch("app.runner.grader.run_python", side_effect=fake_run):
        res = client.post(
            "/api/v1/submissions",
            json={"exercise_id": ex_id, "code": "print(0)"},
            headers=auth_headers(student_token),
        )

    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "failed"
    assert data["passed_count"] == 0
    assert "Expected:" in data["output"]
    assert "Got:" in data["output"]


def test_submission_timeout(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    ex_id = _create_exercise_with_tests(client, teacher_token, auth_headers)

    # Mock run_python simulating infinite loop timeout
    def fake_run_timeout(code: str, input_text: str) -> RunResult:
        return RunResult(stdout="", stderr="", exit_code=None, timed_out=True)

    with patch("app.runner.grader.run_python", side_effect=fake_run_timeout):
        res = client.post(
            "/api/v1/submissions",
            json={"exercise_id": ex_id, "code": "while True: pass"},
            headers=auth_headers(student_token),
        )

    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "timeout"
    assert "Time limit exceeded" in data["output"]


def test_submission_runtime_error(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    ex_id = _create_exercise_with_tests(client, teacher_token, auth_headers)

    def fake_run_error(code: str, input_text: str) -> RunResult:
        return RunResult(
            stdout="",
            stderr="ZeroDivisionError: division by zero",
            exit_code=1,
            timed_out=False,
        )

    with patch("app.runner.grader.run_python", side_effect=fake_run_error):
        res = client.post(
            "/api/v1/submissions",
            json={"exercise_id": ex_id, "code": "print(1/0)"},
            headers=auth_headers(student_token),
        )

    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "error"
    assert "ZeroDivisionError" in data["output"]


def test_submission_access_control(
    client: TestClient,
    teacher_token: str,
    student_token: str,
    other_student_token: str,
    auth_headers,
):
    ex_id = _create_exercise_with_tests(client, teacher_token, auth_headers)

    with patch("app.runner.grader.run_python", return_value=RunResult("16", "", 0, False)):
        sub_res = client.post(
            "/api/v1/submissions",
            json={"exercise_id": ex_id, "code": "print(16)"},
            headers=auth_headers(student_token),
        )
    sub_id = sub_res.json()["id"]

    # Student 1 can view own submission
    own_res = client.get(f"/api/v1/submissions/{sub_id}", headers=auth_headers(student_token))
    assert own_res.status_code == 200

    # Student 2 cannot view Student 1's submission (404 expected for confidentiality)
    other_res = client.get(
        f"/api/v1/submissions/{sub_id}",
        headers=auth_headers(other_student_token),
    )
    assert other_res.status_code == 404

    # Teacher CAN view student's submission
    teacher_view = client.get(
        f"/api/v1/submissions/{sub_id}",
        headers=auth_headers(teacher_token),
    )
    assert teacher_view.status_code == 200


def test_submission_rate_limiting(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    reset_rate_limits()
    ex_id = _create_exercise_with_tests(client, teacher_token, auth_headers)

    with patch("app.runner.grader.run_python", return_value=RunResult("16", "", 0, False)):
        for _ in range(10):
            res = client.post(
                "/api/v1/submissions",
                json={"exercise_id": ex_id, "code": "print(16)"},
                headers=auth_headers(student_token),
            )
            assert res.status_code == 201

        # 11th request triggers rate limiter
        blocked = client.post(
            "/api/v1/submissions",
            json={"exercise_id": ex_id, "code": "print(16)"},
            headers=auth_headers(student_token),
        )
        assert blocked.status_code == 429
        assert "rate limit exceeded" in blocked.json()["detail"].lower()
