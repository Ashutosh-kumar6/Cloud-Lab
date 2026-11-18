import io
from fastapi.testclient import TestClient


def test_upload_valid_file(client: TestClient, student_token: str, auth_headers):
    file_content = b"print('Hello, Cloud Lab!')\n"
    response = client.post(
        "/api/v1/files",
        files={"file": ("solution.py", io.BytesIO(file_content), "text/x-python")},
        headers=auth_headers(student_token),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "solution.py"
    assert data["size_bytes"] == len(file_content)
    assert "id" in data


def test_upload_reject_disallowed_extension(
    client: TestClient, student_token: str, auth_headers
):
    response = client.post(
        "/api/v1/files",
        files={"file": ("malware.exe", io.BytesIO(b"binary data"), "application/octet-stream")},
        headers=auth_headers(student_token),
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


def test_upload_reject_oversized_file(client: TestClient, student_token: str, auth_headers):
    # 1MB + 10 bytes
    large_payload = b"A" * (1_000_000 + 10)
    response = client.post(
        "/api/v1/files",
        files={"file": ("huge_data.txt", io.BytesIO(large_payload), "text/plain")},
        headers=auth_headers(student_token),
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


def test_upload_reject_path_traversal_filename(
    client: TestClient, student_token: str, auth_headers
):
    response = client.post(
        "/api/v1/files",
        files={"file": ("../../etc/passwd.txt", io.BytesIO(b"root:x:0:0\n"), "text/plain")},
        headers=auth_headers(student_token),
    )
    # The filename must be sanitized or rejected; if sanitized, it should not escape or have forbidden traversal
    if response.status_code == 201:
        assert response.json()["filename"] == "passwd.txt"
        assert ".." not in response.json()["filename"]
    else:
        assert response.status_code == 400


def test_upload_reject_binary_executable_magic_bytes(
    client: TestClient, student_token: str, auth_headers
):
    # Windows executable (MZ header) disguised as .txt
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00"
    response = client.post(
        "/api/v1/files",
        files={"file": ("test.txt", io.BytesIO(fake_exe), "text/plain")},
        headers=auth_headers(student_token),
    )
    assert response.status_code == 400
    assert "signature" in response.json()["detail"].lower() or "binary" in response.json()["detail"].lower()


def test_upload_reject_null_byte_binary_payload(
    client: TestClient, student_token: str, auth_headers
):
    payload_with_null = b"def run():\n\x00\x01\x02\x03"
    response = client.post(
        "/api/v1/files",
        files={"file": ("bad_script.py", io.BytesIO(payload_with_null), "text/x-python")},
        headers=auth_headers(student_token),
    )
    assert response.status_code == 400
    assert "binary" in response.json()["detail"].lower()


def test_list_and_download_file(client: TestClient, student_token: str, auth_headers):
    content = b"# Lab 1\nimport math\nprint(math.pi)\n"
    up_res = client.post(
        "/api/v1/files",
        files={"file": ("lab1.py", io.BytesIO(content), "text/x-python")},
        headers=auth_headers(student_token),
    )
    file_id = up_res.json()["id"]

    # List files
    list_res = client.get("/api/v1/files", headers=auth_headers(student_token))
    assert list_res.status_code == 200
    files = list_res.json()
    assert any(f["id"] == file_id and f["filename"] == "lab1.py" for f in files)

    # Download file
    down_res = client.get(f"/api/v1/files/{file_id}/download", headers=auth_headers(student_token))
    assert down_res.status_code == 200
    assert down_res.content == content


def test_delete_file(client: TestClient, student_token: str, auth_headers):
    up_res = client.post(
        "/api/v1/files",
        files={"file": ("temp.py", io.BytesIO(b"x = 1\n"), "text/x-python")},
        headers=auth_headers(student_token),
    )
    file_id = up_res.json()["id"]

    del_res = client.delete(f"/api/v1/files/{file_id}", headers=auth_headers(student_token))
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    # After delete, download should return 404
    get_res = client.get(f"/api/v1/files/{file_id}/download", headers=auth_headers(student_token))
    assert get_res.status_code == 404


def test_user_cannot_access_other_users_file(
    client: TestClient, student_token: str, other_student_token: str, auth_headers
):
    # Student 1 uploads a file
    up_res = client.post(
        "/api/v1/files",
        files={"file": ("private_notes.txt", io.BytesIO(b"Confidential notes\n"), "text/plain")},
        headers=auth_headers(student_token),
    )
    file_id = up_res.json()["id"]

    # Student 2 cannot download Student 1's file (404 expected to prevent resource enumeration)
    down_res = client.get(
        f"/api/v1/files/{file_id}/download",
        headers=auth_headers(other_student_token),
    )
    assert down_res.status_code == 404

    # Student 2 cannot delete Student 1's file
    del_res = client.delete(
        f"/api/v1/files/{file_id}",
        headers=auth_headers(other_student_token),
    )
    assert del_res.status_code == 404

    # Student 2's file list should NOT include Student 1's file
    list_res = client.get("/api/v1/files", headers=auth_headers(other_student_token))
    assert list_res.status_code == 200
    assert not any(f["id"] == file_id for f in list_res.json())
