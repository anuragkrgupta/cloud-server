def test_register_user_success(client):
    response = client.post(
        "/api/register",
        json={"name": "Test_User", "email": "test@example.com", "password": "SecurePassword123"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"

def test_register_duplicate_email(client):
    client.post(
        "/api/register",
        json={"name": "Test_User_2", "email": "test2@example.com", "password": "SecurePassword123"}
    )
    response = client.post(
        "/api/register",
        json={"name": "Test_User_2", "email": "test2@example.com", "password": "SecurePassword123"}
    )
    assert response.status_code == 409

def test_login_user_success(client):
    client.post(
        "/api/register",
        json={"name": "Test_User_3", "email": "test3@example.com", "password": "SecurePassword123"}
    )
    response = client.post(
        "/api/login",
        json={"email": "test3@example.com", "password": "SecurePassword123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data

def test_login_user_invalid_password(client):
    response = client.post(
        "/api/login",
        json={"email": "test@example.com", "password": "WrongPassword123"}
    )
    assert response.status_code == 401

def test_protected_route_unauthenticated(client):
    client.cookies.clear()
    response = client.get("/api/me")
    assert response.status_code == 401

def test_protected_route_authenticated(client):
    client.post(
        "/api/register",
        json={"name": "Test_User_4", "email": "test4@example.com", "password": "SecurePassword123"}
    )
    login_response = client.post(
        "/api/login",
        json={"email": "test4@example.com", "password": "SecurePassword123"}
    )
    token = login_response.json()["access_token"]
    
    response = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "test4@example.com"
