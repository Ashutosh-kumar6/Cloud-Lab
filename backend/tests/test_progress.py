from unittest.mock import patch

from fastapi.testclient import TestClient

from app.runner.sandbox import RunResult


def test_notes_crud(client: TestClient, teacher_token: str, student_token: str, auth_headers):
    # 1. Teacher creates a note
    create_res = client.post(
        "/api/v1/notes",
        json={
            "title": "Python Basics Reference",
            "topic": "basics",
            "body": "Remember that Python uses 0-based indexing.",
        },
        headers=auth_headers(teacher_token),
    )
    assert create_res.status_code == 201
    note_id = create_res.json()["id"]

    # 2. Student lists notes
    list_res = client.get("/api/v1/notes", headers=auth_headers(student_token))
    assert list_res.status_code == 200
    notes = list_res.json()
    assert len(notes) >= 1
    assert any(n["id"] == note_id for n in notes)

    # 3. Student reads note detail
    detail_res = client.get(f"/api/v1/notes/{note_id}", headers=auth_headers(student_token))
    assert detail_res.status_code == 200
    data = detail_res.json()
    assert data["title"] == "Python Basics Reference"
    assert "0-based indexing" in data["body"]


def test_progress_streaks_and_topics(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    # Create an exercise
    ex_res = client.post(
        "/api/v1/admin/exercises",
        json={
            "title": "Topic Math Test",
            "topic": "math",
            "difficulty": "easy",
            "description": "Calculate something",
            "test_cases": [{"input_text": "1", "expected_output": "1", "is_hidden": False}],
        },
        headers=auth_headers(teacher_token),
    )
    ex_id = ex_res.json()["id"]

    # Initial progress: 0 submissions
    initial = client.get("/api/v1/progress/me", headers=auth_headers(student_token))
    assert initial.status_code == 200
    pdata = initial.json()
    assert pdata["total_submissions"] == 0
    assert pdata["solved_exercises"] == 0

    # Submit passed code
    with patch("app.runner.grader.run_python", return_value=RunResult("1", "", 0, False)):
        sub_res = client.post(
            "/api/v1/submissions",
            json={"exercise_id": ex_id, "code": "print(1)"},
            headers=auth_headers(student_token),
        )
        assert sub_res.status_code == 201

    # Updated progress
    updated = client.get("/api/v1/progress/me", headers=auth_headers(student_token))
    assert updated.status_code == 200
    updata = updated.json()
    assert updata["total_submissions"] == 1
    assert updata["solved_exercises"] == 1
    assert updata["current_streak"] == 1
    assert len(updata["topics"]) >= 1

    topic_math = next(t for t in updata["topics"] if t["topic"] == "math")
    assert topic_math["accuracy_percent"] == 100.0
    assert topic_math["solved_exercises"] == 1


def test_recommendations(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    # Create exercise in loop topic
    client.post(
        "/api/v1/admin/exercises",
        json={
            "title": "While loop drill",
            "topic": "loops",
            "difficulty": "easy",
            "description": "Count up to n",
            "test_cases": [{"input_text": "3", "expected_output": "3", "is_hidden": False}],
        },
        headers=auth_headers(teacher_token),
    )

    rec_res = client.get("/api/v1/recommendations/me", headers=auth_headers(student_token))
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    assert "message" in rec_data
    assert "recommended_exercises" in rec_data
    assert len(rec_data["recommended_exercises"]) >= 1
