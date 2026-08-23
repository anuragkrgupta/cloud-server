import pytest
from unittest.mock import patch, AsyncMock

def get_auth_token_with_telegram(client):
    client.post("/api/register", json={"name": "File_User", "email": "fileuser@example.com", "password": "SecurePassword123"})
    response = client.post("/api/login", json={"email": "fileuser@example.com", "password": "SecurePassword123"})
    token = response.json()["access_token"]
    
    with patch("app.routes.telegram.check_qr_login_status") as mock_check_status:
        mock_check_status.return_value = {
            "status": "success",
            "session_string": "fake_session",
            "channel_id": "123456",
            "tg_user_id": "789"
        }
        client.get("/api/telegram/qr-status?token=fake", headers={"Authorization": f"Bearer {token}"})
        
    return token

@patch("app.routes.files.upload_chunk_to_telegram", new_callable=AsyncMock)
def test_upload_chunk(mock_upload, client):
    token = get_auth_token_with_telegram(client)
    
    response = client.post(
        "/api/upload/chunk",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file_id": 1,
            "start_part_index": 0,
            "total_parts": 1,
            "is_big": False
        },
        files={"file": ("test.txt", b"hello world")}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    mock_upload.assert_called_once()

def test_complete_upload_and_get_files(client):
    token = get_auth_token_with_telegram(client)
    
    response = client.post(
        "/api/upload/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "filename": "my_document.pdf",
            "file_size": 1024,
            "mime_type": "application/pdf",
            "message_ids": [42]
        }
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
