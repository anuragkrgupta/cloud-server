"""
Tests verifying exception handling across routes, middleware, and services.
Ensures that:
- Unexpected exceptions do not leak stack traces, secrets, or internal str(e) to clients.
- Proper HTTP status codes are returned (500 for internal errors, 502 for external Telegram failure, 400 for bad state/revocation).
- Database transactions are rolled back on failure.
- Session revocation cleanly resets user telegram_session.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy.exc import OperationalError
from telethon.errors import SessionRevokedError

from app.models import User, FileRecord, FilePartRecord
from tests.conftest import CSRF_HEADER, TestingSessionLocal


def create_authenticated_user(client, email="ex_user@example.com", name="Ex_User"):
    client.post(
        "/api/register",
        json={"name": name, "email": email, "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    res = client.post(
        "/api/login",
        json={"email": email, "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    token = res.json()["access_token"]
    return token


def test_telegram_session_revocation_handling(client):
    """When a session revocation error occurs, user session is cleared and 400 is returned."""
    token = create_authenticated_user(client, "revoked@example.com", "Revoked_User")
    
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "revoked@example.com").first()
        user.telegram_session = "gAAAAA_fake_encrypted_session"
        user.channel_id = "-100123456789"
        db.commit()
        
        file_rec = FileRecord(
            user_id=user.id,
            original_name="test.txt",
            file_size=100,
            mime_type="text/plain",
        )
        db.add(file_rec)
        db.commit()
        
        part = FilePartRecord(
            file_id=file_rec.id,
            part_index=0,
            telegram_message_id=999,
            channel_id=user.channel_id,
        )
        db.add(part)
        db.commit()
        file_id = file_rec.id
    finally:
        db.close()

    with patch("app.routes.files.download_multiple_messages_stream", new_callable=AsyncMock) as mock_stream:
        mock_stream.side_effect = SessionRevokedError(request=None)
        
        response = client.get(
            f"/api/download/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400
        assert "Telegram session expired or revoked" in response.json()["detail"]
        
        # Verify session was cleared in database
        check_db = TestingSessionLocal()
        try:
            user_check = check_db.query(User).filter(User.email == "revoked@example.com").first()
            assert user_check.telegram_session is None
        finally:
            check_db.close()


def test_telegram_unexpected_error_does_not_leak_details(client):
    """When an unexpected Telegram error occurs, HTTP 502 with safe generic message is returned."""
    token = create_authenticated_user(client, "generic_err@example.com", "Generic_User")
    
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "generic_err@example.com").first()
        user.telegram_session = "gAAAAA_fake_session"
        user.channel_id = "-100123456789"
        db.commit()
        
        file_rec = FileRecord(
            user_id=user.id,
            original_name="secret.txt",
            file_size=100,
            mime_type="text/plain",
        )
        db.add(file_rec)
        db.commit()

        part = FilePartRecord(
            file_id=file_rec.id,
            part_index=0,
            telegram_message_id=999,
            channel_id=user.channel_id,
        )
        db.add(part)
        db.commit()
        file_id = file_rec.id
    finally:
        db.close()

    with patch("app.routes.files.download_multiple_messages_stream", new_callable=AsyncMock) as mock_stream:
        # Simulate an internal Telethon error with potentially sensitive details
        mock_stream.side_effect = RuntimeError("Internal connection secret=XYZ123 failed")
        
        response = client.get(
            f"/api/download/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 502
        assert "XYZ123" not in response.json()["detail"]
        assert response.json()["detail"] == "Telegram operation failed. Please try again."


def test_complete_upload_db_failure_rolls_back_and_returns_500(client):
    """When DB fails during complete_upload, transaction is rolled back and safe 500 is returned."""
    token = create_authenticated_user(client, "db_fail@example.com", "DB_Fail_User")
    
    with patch("sqlalchemy.orm.Session.commit", side_effect=OperationalError("mock db error", {}, None)):
        response = client.post(
            "/api/upload/complete",
            json={
                "filename": "failed.txt",
                "file_size": 1234,
                "mime_type": "text/plain",
                "message_ids": [1, 2],
            },
            headers={"Authorization": f"Bearer {token}", **CSRF_HEADER},
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to save upload record. Please try again."
        assert "OperationalError" not in response.json()["detail"]


def test_shared_file_stream_error_returns_safe_500(client):
    """When shared file streaming fails, safe 500 is returned without internal exception leakage."""
    db = TestingSessionLocal()
    try:
        owner = User(
            name="Owner_User",
            email="owner_shared@example.com",
            password="hashed_password",
            telegram_session="gAAAAA_fake_session",
            channel_id="-100987654321",
        )
        db.add(owner)
        db.commit()
        
        file_rec = FileRecord(
            user_id=owner.id,
            original_name="shared_doc.pdf",
            file_size=5000,
            mime_type="application/pdf",
            is_shared=True,
            share_token="safe-test-token-1234",
        )
        db.add(file_rec)
        db.commit()

        part = FilePartRecord(
            file_id=file_rec.id,
            part_index=0,
            telegram_message_id=888,
            channel_id=owner.channel_id,
        )
        db.add(part)
        db.commit()
    finally:
        db.close()

    with patch("app.routes.share.download_multiple_messages_stream", new_callable=AsyncMock) as mock_stream:
        mock_stream.side_effect = Exception("Internal RPC failure: auth_key_dead_secret_token")
        
        response = client.get("/api/shared/safe-test-token-1234/download")
        assert response.status_code == 500
        assert "auth_key_dead_secret_token" not in response.json()["detail"]
        assert response.json()["detail"] == "Failed to stream file. Please try again."


def test_telegram_phone_start_error_does_not_leak_str_e(client):
    """api_phone_start returns safe 400 without leaking exception internals."""
    token = create_authenticated_user(client, "phone_start@example.com", "Phone_Start")
    
    with patch("app.routes.telegram.start_phone_login", new_callable=AsyncMock) as mock_login:
        mock_login.side_effect = Exception("Detailed internal stack trace / secret API key")
        
        response = client.post(
            "/api/telegram/phone-start",
            json={"phone_number": "+1234567890"},
            headers={"Authorization": f"Bearer {token}", **CSRF_HEADER},
        )
        assert response.status_code == 400
        assert "Detailed internal stack trace" not in response.json()["detail"]
        assert response.json()["detail"] == "Failed to send verification code. Please try again."


def test_telegram_phone_code_error_returns_safe_500(client):
    """api_phone_code returns safe 500 without leaking exception internals."""
    token = create_authenticated_user(client, "phone_code@example.com", "Phone_Code")
    
    with patch("app.routes.telegram.submit_phone_code", new_callable=AsyncMock) as mock_submit:
        mock_submit.side_effect = Exception("Internal crypto failure")
        
        response = client.post(
            "/api/telegram/phone-code",
            json={"token": "fake_token", "phone_code": "12345"},
            headers={"Authorization": f"Bearer {token}", **CSRF_HEADER},
        )
        assert response.status_code == 500
        assert "Internal crypto failure" not in response.json()["detail"]
        assert response.json()["detail"] == "An unexpected error occurred while verifying the code."


def test_telegram_qr_start_error_returns_safe_400(client):
    """api_qr_start returns safe 400 without leaking exception internals."""
    token = create_authenticated_user(client, "qr_start@example.com", "QR_Start")
    
    with patch("app.routes.telegram.start_qr_login", new_callable=AsyncMock) as mock_qr:
        mock_qr.side_effect = Exception("Telethon flood wait: 99999s")
        
        response = client.post(
            "/api/telegram/qr-start",
            headers={"Authorization": f"Bearer {token}", **CSRF_HEADER},
        )
        assert response.status_code == 400
        assert "Telethon flood wait" not in response.json()["detail"]
        assert response.json()["detail"] == "Failed to start QR login. Please try again."


@pytest.mark.asyncio
async def test_background_transfer_rollback_on_exception():
    """transfer_file_between_users rolls back DB session on exception."""
    from app.services.transfer import transfer_file_between_users
    
    mock_db = MagicMock()
    mock_user = MagicMock()
    mock_user.is_telegram_connected = True
    mock_user.telegram_session = "fake_session"
    mock_user.channel_id = "-100123"
    
    mock_file = MagicMock()
    mock_file.original_name = "test.bin"
    mock_file.file_size = 1000
    mock_file.mime_type = "application/octet-stream"
    
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        mock_user,  # source_user
        mock_user,  # target_user
        mock_file,  # source_file
    ]
    
    with patch("app.services.transfer.SessionLocal", return_value=mock_db), \
         patch("app.services.transfer.get_client_for_session", side_effect=RuntimeError("Connection lost")):
        
        await transfer_file_between_users(1, 2, 10, [101])
        
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()
