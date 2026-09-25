"""Tests for registration, login, logout, /api/me, and CORS."""
from tests.conftest import CSRF_HEADER, _merge_headers


def test_register_user_success(client):
    response = client.post(
        "/api/register",
        json={"name": "Test_User", "email": "test@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"


def test_register_duplicate_email(client):
    client.post(
        "/api/register",
        json={"name": "Test_User_2", "email": "test2@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    response = client.post(
        "/api/register",
        json={"name": "Test_User_2", "email": "test2@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    assert response.status_code == 409


def test_register_weak_password(client):
    """Pydantic schema rejects passwords that don't meet complexity rules."""
    response = client.post(
        "/api/register",
        json={"name": "Weak_User", "email": "weak@example.com", "password": "short"},
        headers=CSRF_HEADER,
    )
    assert response.status_code == 422  # Pydantic validation error


def test_register_invalid_name(client):
    """Name must be 3-50 chars, alphanumeric + underscore only."""
    response = client.post(
        "/api/register",
        json={"name": "ab", "email": "bad_name@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    assert response.status_code == 422


def test_login_user_success(client):
    client.post(
        "/api/register",
        json={"name": "Test_User_3", "email": "test3@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    response = client.post(
        "/api/login",
        json={"email": "test3@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_user_invalid_password(client):
    response = client.post(
        "/api/login",
        json={"email": "test@example.com", "password": "WrongPassword123"},
        headers=CSRF_HEADER,
    )
    assert response.status_code == 401


def test_login_nonexistent_email(client):
    response = client.post(
        "/api/login",
        json={"email": "nobody@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    assert response.status_code == 401


def test_protected_route_unauthenticated(client):
    client.cookies.clear()
    response = client.get("/api/me")
    assert response.status_code == 401


def test_protected_route_with_bearer(client):
    """Auth via Authorization: Bearer header."""
    client.post(
        "/api/register",
        json={"name": "Test_User_4", "email": "test4@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    login_response = client.post(
        "/api/login",
        json={"email": "test4@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    token = login_response.json()["access_token"]

    response = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "test4@example.com"
    assert "is_telegram_connected" in response.json()


def test_protected_route_with_cookie(client):
    """Auth via httpOnly cookie set by /api/login."""
    client.post(
        "/api/register",
        json={"name": "Cookie_User", "email": "cookie@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    login_response = client.post(
        "/api/login",
        json={"email": "cookie@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    assert login_response.status_code == 200
    # TestClient auto-stores cookies, so /api/me should work without Bearer
    response = client.get("/api/me")
    assert response.status_code == 200
    assert response.json()["email"] == "cookie@example.com"


def test_logout_clears_cookie(client):
    """After logout, /api/me should return 401."""
    client.post(
        "/api/register",
        json={"name": "Logout_User", "email": "logout@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    client.post(
        "/api/login",
        json={"email": "logout@example.com", "password": "SecurePassword123"},
        headers=CSRF_HEADER,
    )
    logout_response = client.post("/api/logout", headers=CSRF_HEADER)
    assert logout_response.status_code == 200

    me_response = client.get("/api/me")
    assert me_response.status_code == 401


def test_csrf_blocks_post_without_header(client):
    """POST to an /api/ route without X-Requested-With must return 403."""
    response = client.post(
        "/api/register",
        json={"name": "CSRF_Test", "email": "csrf@example.com", "password": "SecurePassword123"},
        # Intentionally NO X-Requested-With header
    )
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_csrf_allows_get_without_header(client):
    """/api/me is GET — CSRF middleware must NOT block it."""
    # No X-Requested-With, but GET is safe method
    response = client.get("/api/me")
    # 401 because not authenticated, but NOT 403
    assert response.status_code == 401


def test_cors_preflight_allowed_origin(client):
    """CORS preflight from a configured origin should succeed."""
    # In test env ALLOWED_ORIGINS is unset, so defaults include localhost:5500
    allowed_origin = "http://localhost:5500"
    response = client.options(
        "/api/me",
        headers={
            "Origin": allowed_origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-requested-with",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_preflight_disallowed_origin(client):
    """CORS preflight from an unknown origin should NOT allow credentials."""
    response = client.options(
        "/api/me",
        headers={
            "Origin": "https://evil.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    # Starlette returns 400 for disallowed origins
    assert response.status_code == 400
