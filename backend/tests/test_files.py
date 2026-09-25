"""Tests for file upload, complete, and listing (mocked Telegram interactions)."""
import pytest
from unittest.mock import patch, AsyncMock
from tests.conftest import CSRF_HEADER


def get_auth_token_with_telegram(client):
    """Register, login, and simulate a successful Telegram connection."""
    client.post(
        "/api/register",
        json={"name": "File_User", "email": "fileuser@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    response = client.post(
        "/api/login",
        json={"email": "fileuser@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    token = response.json()["access_token"]

    with patch("app.routes.telegram.check_qr_login_status") as mock_check_status:
        mock_check_status.return_value = {
            "status": "success",
            "session_string": "fake_session",
            "channel_id": "123456",
            "tg_user_id": "789",
        }
        client.get(
            "/api/telegram/qr-status?token=fake",
            headers={"Authorization": f"Bearer {token}"},
        )

    return token


@patch("app.services.telegram_service.upload_stream_to_telegram", new_callable=AsyncMock)
def test_upload_stream(mock_upload, client):
    mock_upload.return_value = 42
    token = get_auth_token_with_telegram(client)

    content = b"hello world stream"
    response = client.post(
        "/api/upload/stream?filename=test.txt",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Length": str(len(content)),
            **CSRF_HEADER,
        },
        content=content,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["message_id"] == 42
    mock_upload.assert_called_once()


def test_complete_upload_and_get_files(client):
    token = get_auth_token_with_telegram(client)

    response = client.post(
        "/api/upload/complete",
        headers={"Authorization": f"Bearer {token}", **CSRF_HEADER},
        json={
            "filename": "my_document.pdf",
            "file_size": 1024,
            "mime_type": "application/pdf",
            "message_ids": [42],
        },
    )

    assert response.status_code == 200
    file_record = response.json()
    assert file_record["original_name"] == "my_document.pdf"

    get_resp = client.get("/api/files", headers={"Authorization": f"Bearer {token}"})
    assert get_resp.status_code == 200
    files = get_resp.json()
    assert len(files) == 1
    assert files[0]["original_name"] == "my_document.pdf"
    assert files[0]["id"] == file_record["id"]


def test_files_list_unauthenticated(client):
    """GET /api/files without auth must return 401."""
    client.cookies.clear()
    response = client.get("/api/files")
    assert response.status_code == 401
