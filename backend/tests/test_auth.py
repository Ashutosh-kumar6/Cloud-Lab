from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jose import jwt

from app.core.config import settings
from app.core.rate_limit import reset_rate_limits
from app.models.user import User


def test_register_success(client: TestClient):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "newbie@cloudlab.edu", "password": "securepassword123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newbie@cloudlab.edu"
    assert data["role"] == "student"
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data


def test_register_duplicate_email(client: TestClient, student_user: User):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": student_user.email, "password": "anotherpassword"},
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


def test_register_short_password(client: TestClient):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "short@cloudlab.edu", "password": "123"},
    )
    assert response.status_code == 400
    assert "at least 6 characters" in response.json()["detail"]


def test_register_too_long_password(client: TestClient):
    long_pw = "a" * 75
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "long@cloudlab.edu", "password": long_pw},
    )
    assert response.status_code == 400
    assert "exceed 72 bytes" in response.json()["detail"]


def test_login_success(client: TestClient, student_user: User):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": student_user.email, "password": "student123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client: TestClient, student_user: User):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": student_user.email, "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert "wrong email or password" in response.json()["detail"].lower()


def test_login_nonexistent_user(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "ghost@cloudlab.edu", "password": "anypassword"},
    )
    assert response.status_code == 401
    assert "wrong email or password" in response.json()["detail"].lower()


def test_invalid_jwt_token(client: TestClient):
    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    assert response.status_code == 401
    assert "invalid or expired token" in response.json()["detail"].lower()


def test_expired_jwt_token(client: TestClient, student_user: User):
    # Craft an expired token
    expired = datetime.now(timezone.utc) - timedelta(minutes=10)
    payload = {"sub": str(student_user.id), "role": student_user.role, "exp": expired}
    expired_token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "invalid or expired token" in response.json()["detail"].lower()


def test_login_rate_limiting(client: TestClient, student_user: User):
    reset_rate_limits()
    # 10 attempts allowed per window
    for _ in range(10):
        client.post(
            "/api/v1/auth/login",
            data={"username": student_user.email, "password": "wrongpassword"},
        )
    # 11th attempt should trigger 429
    blocked = client.post(
        "/api/v1/auth/login",
        data={"username": student_user.email, "password": "student123"},
    )
    assert blocked.status_code == 429
    assert "too many login attempts" in blocked.json()["detail"].lower()
