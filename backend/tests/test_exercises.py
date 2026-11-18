from fastapi.testclient import TestClient


def _create_exercise(client: TestClient, teacher_token: str, auth_headers):
    return client.post(
        "/api/v1/admin/exercises",
        json={
            "title": "Factorial",
            "topic": "recursion",
            "difficulty": "medium",
            "description": "Calculate n!",
            "test_cases": [
                {"input_text": "3", "expected_output": "6", "is_hidden": False},
                {"input_text": "5", "expected_output": "120", "is_hidden": True},
                {"input_text": "0", "expected_output": "1", "is_hidden": True},
            ],
        },
        headers=auth_headers(teacher_token),
    )


def test_list_exercises(client: TestClient, teacher_token: str, student_token: str, auth_headers):
    res = _create_exercise(client, teacher_token, auth_headers)
    assert res.status_code == 201

    # Student lists exercises
    list_res = client.get("/api/v1/exercises", headers=auth_headers(student_token))
    assert list_res.status_code == 200
    exercises = list_res.json()
    assert len(exercises) >= 1
    item = exercises[0]
    assert "id" in item
    assert "title" in item
    assert "topic" in item
    assert "difficulty" in item


def test_list_exercises_filtered(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    _create_exercise(client, teacher_token, auth_headers)

    # Filter matching
    res = client.get(
        "/api/v1/exercises?topic=recursion&difficulty=medium",
        headers=auth_headers(student_token),
    )
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # Filter non-matching
    res_empty = client.get(
        "/api/v1/exercises?topic=graphs",
        headers=auth_headers(student_token),
    )
    assert res_empty.status_code == 200
    assert len(res_empty.json()) == 0


def test_get_exercise_detail_never_reveals_hidden_tests(
    client: TestClient, teacher_token: str, student_token: str, auth_headers
):
    create_res = _create_exercise(client, teacher_token, auth_headers)
    ex_id = create_res.json()["id"]

    # Student requests exercise detail
    detail_res = client.get(
        f"/api/v1/exercises/{ex_id}",
        headers=auth_headers(student_token),
    )
    assert detail_res.status_code == 200
    data = detail_res.json()

    assert data["title"] == "Factorial"
    assert data["description"] == "Calculate n!"
    assert "sample_test_cases" in data

    # Only 1 sample test was non-hidden (input: "3")
    assert len(data["sample_test_cases"]) == 1
    sample = data["sample_test_cases"][0]
    assert sample["input_text"] == "3"
    assert sample["expected_output"] == "6"

    # Crucial security check: Ensure the hidden inputs ("5", "0") are nowhere in the response!
    raw_content = detail_res.text
    assert "120" not in raw_content
    assert '"is_hidden"' not in raw_content


def test_get_nonexistent_exercise(client: TestClient, student_token: str, auth_headers):
    res = client.get("/api/v1/exercises/99999", headers=auth_headers(student_token))
    assert res.status_code == 404
