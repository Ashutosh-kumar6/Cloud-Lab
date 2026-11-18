import io
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import ALGORITHM, create_access_token
from app.services import storage


# ── Area 1: File Uploads & Path Traversal ─────────────────────────────────────

def test_file_upload_streaming_rejects_oversized_content(
    client: TestClient, student_token: str, auth_headers
):
    # Create stream exceeding 1 MB (1,000,001 bytes)
    big_content = b"A" * 1_000_001
    file_payload = {"file": ("big_stream.txt", io.BytesIO(big_content), "text/plain")}

    res = client.post(
        "/api/v1/files",
        files=file_payload,
        headers=auth_headers(student_token),
    )
    assert res.status_code == 413
    assert "too large" in res.json()["detail"].lower()


def test_storage_path_of_blocks_path_traversal():
    with pytest.raises(ValueError, match="Invalid storage identifier"):
        storage.path_of("../etc/passwd")

    with pytest.raises(ValueError, match="Invalid storage identifier"):
        storage.path_of("/absolute/path")

    with pytest.raises(ValueError, match="Invalid storage identifier"):
        storage.path_of("..\\windows\\win.ini")


def test_storage_path_of_blocks_symlinks(tmp_path):
    # Verify that a symlink inside storage directory is caught
    valid_hex = "a" * 32
    target_file = tmp_path / "target.txt"
    target_file.write_text("secret")

    with patch.object(storage, "STORAGE_DIR", tmp_path):
        symlink_path = tmp_path / valid_hex
        try:
            symlink_path.symlink_to(target_file)
            with pytest.raises(ValueError, match="Symlink traversal detected"):
                storage.path_of(valid_hex)
        except OSError:
            # On Windows without developer mode / elevated privileges symlinks can raise OSError
            pass


# ── Area 2: Code Runner Sandbox ───────────────────────────────────────────────

def test_sandbox_guarantees_container_cleanup():
    from app.runner.sandbox import run_python

    mock_container = MagicMock()
    mock_container.wait.side_effect = Exception("Docker communication broken")
    mock_container.logs.return_value = b""

    mock_docker_client = MagicMock()
    mock_docker_client.containers.create.return_value = mock_container

    with patch("docker.from_env", return_value=mock_docker_client):
        result = run_python("print(1)", "")
        assert result.timed_out is True
        # Verify force cleanup was invoked
        mock_container.remove.assert_called_once_with(force=True)


# ── Area 3: Auth & JWT Hardening ──────────────────────────────────────────────

def test_settings_rejects_insecure_or_empty_jwt_secret():
    # Production without 32+ char secret
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="short", cors_origins="http://localhost")

    # Production with 'change-me-later'
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="change-me-later", cors_origins="http://localhost")

    # Development without secret
    with pytest.raises(ValidationError):
        Settings(environment="development", jwt_secret="", cors_origins="http://localhost")


def test_tampered_jwt_token_rejected(client: TestClient):
    # Token signed with a different key
    bad_token = jwt.encode({"sub": "1", "role": "student"}, "wrong-secret-key-123456789012345678", algorithm=ALGORITHM)
    res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {bad_token}"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid or expired token"


def test_expired_jwt_token_rejected(client: TestClient):
    past_exp = int(time.time()) - 3600
    expired_token = jwt.encode({"sub": "1", "role": "student", "exp": past_exp}, "test-secret-key-that-is-at-least-32-characters-long", algorithm=ALGORITHM)
    res = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid or expired token"


def test_login_error_message_is_uniform(client: TestClient, student_user):
    # Nonexistent user
    res1 = client.post("/api/v1/auth/login", data={"username": "does_not_exist@cloudlab.edu", "password": "wrong"})
    assert res1.status_code == 401
    assert res1.json()["detail"] == "Wrong email or password"

    # Existing user with wrong password
    res2 = client.post("/api/v1/auth/login", data={"username": student_user.email, "password": "wrongpassword123"})
    assert res2.status_code == 401
    assert res2.json()["detail"] == "Wrong email or password"


def test_register_rate_limiting(client: TestClient):
    from app.core.rate_limit import reset_rate_limits
    reset_rate_limits()

    # Repeated register attempts from same client IP
    responses = []
    for i in range(12):
        r = client.post(
            "/api/v1/auth/register",
            json={"email": f"flood_{i}@cloudlab.edu", "password": "password123"},
        )
        responses.append(r.status_code)

    assert 429 in responses


# ── Area 4: Access Control & IDOR ─────────────────────────────────────────────

def test_admin_route_strictly_enforces_roles(client: TestClient, student_token: str, auth_headers):
    res = client.post(
        "/api/v1/admin/exercises",
        json={"title": "Hacked", "topic": "t", "difficulty": "easy", "description": "d", "test_cases": []},
        headers=auth_headers(student_token),
    )
    assert res.status_code == 403


def test_hidden_test_cases_never_exposed(client: TestClient, teacher_token: str, student_token: str, auth_headers):
    # Create exercise with 1 public and 1 hidden test case
    create_res = client.post(
        "/api/v1/admin/exercises",
        json={
            "title": "Hidden Test Check",
            "topic": "security",
            "difficulty": "easy",
            "description": "desc",
            "test_cases": [
                {"input_text": "public", "expected_output": "out1", "is_hidden": False},
                {"input_text": "secret_hidden", "expected_output": "out2", "is_hidden": True},
            ],
        },
        headers=auth_headers(teacher_token),
    )
    ex_id = create_res.json()["id"]

    # Student requests exercise
    detail_res = client.get(f"/api/v1/exercises/{ex_id}", headers=auth_headers(student_token))
    assert detail_res.status_code == 200
    data = detail_res.json()

    assert len(data["sample_test_cases"]) == 1
    assert data["sample_test_cases"][0]["input_text"] == "public"
    assert "secret_hidden" not in str(data)


# ── Area 5: General Hardening & Security Headers ──────────────────────────────

def test_security_headers_present_in_responses(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "default-src 'self'" in res.headers.get("Content-Security-Policy", "")
    assert "max-age=31536000" in res.headers.get("Strict-Transport-Security", "")


def test_cors_rejects_wildcard():
    with pytest.raises(ValidationError, match="CORS cannot allow '\\*'"):
        Settings(environment="production", jwt_secret="a" * 32, cors_origins="*")


def test_internal_server_error_does_not_leak_traceback(client: TestClient, student_token: str, auth_headers):
    # TestClient with raise_server_exceptions=False receives the 500 response from FastAPI
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as safe_client:
        with patch("app.api.v1.exercises.select", side_effect=RuntimeError("Secret internal database password leaked!")):
            res = safe_client.get("/api/v1/exercises", headers=auth_headers(student_token))
            assert res.status_code == 500
            assert res.json() == {"detail": "Internal server error"}
            assert "Secret" not in res.text
