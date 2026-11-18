from fastapi.testclient import TestClient


def test_student_cannot_access_admin_exercises(
    client: TestClient, student_token: str, auth_headers
):
    payload = {
        "title": "Reverse a String",
        "topic": "strings",
        "difficulty": "easy",
        "description": "Write a program that prints the reversed string.",
        "test_cases": [{"input_text": "hello", "expected_output": "olleh", "is_hidden": False}],
    }
    response = client.post(
        "/api/v1/admin/exercises",
        json=payload,
        headers=auth_headers(student_token),
    )
    assert response.status_code == 403
    assert "not enough permissions" in response.json()["detail"].lower()


def test_student_cannot_create_note(client: TestClient, student_token: str, auth_headers):
    payload = {
        "title": "Unauthorized Note",
        "topic": "python",
        "body": "Students should not be creating official notes.",
    }
    response = client.post(
        "/api/v1/notes",
        json=payload,
        headers=auth_headers(student_token),
    )
    assert response.status_code == 403
    assert "not enough permissions" in response.json()["detail"].lower()


def test_teacher_can_create_exercise(client: TestClient, teacher_token: str, auth_headers):
    payload = {
        "title": "Sum Two Numbers",
        "topic": "basics",
        "difficulty": "easy",
        "description": "Read two integers and print their sum.",
        "test_cases": [
            {"input_text": "2\n3", "expected_output": "5", "is_hidden": False},
            {"input_text": "-1\n1", "expected_output": "0", "is_hidden": True},
        ],
    }
    response = client.post(
        "/api/v1/admin/exercises",
        json=payload,
        headers=auth_headers(teacher_token),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Sum Two Numbers"
    assert data["topic"] == "basics"


def test_admin_can_create_exercise(client: TestClient, admin_token: str, auth_headers):
    payload = {
        "title": "Palindrome Checker",
        "topic": "strings",
        "difficulty": "medium",
        "description": "Check if a string is a palindrome.",
        "test_cases": [
            {"input_text": "radar", "expected_output": "True", "is_hidden": False},
        ],
    }
    response = client.post(
        "/api/v1/admin/exercises",
        json=payload,
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Palindrome Checker"
