"""Tests for Telegram QR login flow (mocked — no real Telegram connection)."""
import pytest
from unittest.mock import patch, AsyncMock
from tests.conftest import CSRF_HEADER


def get_auth_token(client):
    client.post(
        "/api/register",
        json={"name": "TG_User", "email": "tg@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    response = client.post(
        "/api/login",
        json={"email": "tg@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    return response.json()["access_token"]


@patch("app.routes.telegram.start_qr_login", new_callable=AsyncMock)
def test_start_telegram_qr_login(mock_start_qr, client):
    mock_start_qr.return_value = ("fake_token_id", "tg://login?token=fake")
    token = get_auth_token(client)

    response = client.post(
        "/api/telegram/qr-start",
        headers={"Authorization": f"Bearer {token}", **CSRF_HEADER},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token"] == "fake_token_id"
    assert data["url"] == "tg://login?token=fake"


@patch("app.routes.telegram.check_qr_login_status")
def test_check_qr_login_status_success(mock_check_status, client):
    token = get_auth_token(client)
    mock_check_status.return_value = {
        "status": "success",
        "session_string": "fake_session",
        "channel_id": "123456",
        "tg_user_id": "789",
    }

    response = client.get(
        "/api/telegram/qr-status?token=fake_token_id",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    me_response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.json()["is_telegram_connected"] == True
