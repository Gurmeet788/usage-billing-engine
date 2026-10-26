
from app.models import User


def test_register_tenant_success(client):
    test_client, TestingSessionLocal = client

    response = test_client.post(
        "/register",
        json={
            "name": "Test Company",
            "email": "owner@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["email"] == "owner@example.com"
    assert data["tenant_id"] is not None
    assert data["id"] is not None

    # Verify that the registered user has the owner role.
    with TestingSessionLocal() as db:
        user = db.query(User).filter(
            User.email == "owner@example.com"
        ).first()

        assert user is not None
        assert user.role == "owner"


def test_register_duplicate_email(client):
    test_client, _ = client

    user_data = {
        "name": "Test Company",
        "email": "owner@example.com",
        "password": "password123",
    }

    first_response = test_client.post(
        "/register", json=user_data
    )

    second_response = test_client.post(
        "/register", json=user_data
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Email already registered"
    )


def test_register_short_password(client):
    test_client, _ = client

    response = test_client.post(
        "/register",
        json={
            "name": "Test Company",
            "email": "owner@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422


def test_login_success(client):
    test_client, _ = client

    # Register an owner first.
    registration = test_client.post(
        "/register",
        json={
            "name": "Login Company",
            "email": "login@example.com",
            "password": "password123",
        },
    )

    assert registration.status_code == 201

    # Log in using the same credentials.
    response = test_client.post(
        "/login",
        json={
            "email": "login@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["token_type"] == "bearer"
    assert data["access_token"]

    # Verify that the returned token actually works.
    me_response = test_client.get(
        "/me",
        headers={
            "Authorization": f"Bearer {data['access_token']}"
        },
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "login@example.com"


def test_login_wrong_password(client):
    test_client, _ = client

    test_client.post(
        "/register",
        json={
            "name": "Login Company",
            "email": "login@example.com",
            "password": "password123",
        },
    )

    response = test_client.post(
        "/login",
        json={
            "email": "login@example.com",
            "password": "wrongpassword",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid email or password"
    )


def test_login_unknown_email(client):
    test_client, _ = client

    response = test_client.post(
        "/login",
        json={
            "email": "unknown@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 401


def test_login_inactive_user(client):
    test_client, TestingSessionLocal = client

    test_client.post(
        "/register",
        json={
            "name": "Inactive Company",
            "email": "inactive@example.com",
            "password": "password123",
        },
    )

    # Deactivate the user directly in the test database.
    with TestingSessionLocal() as db:
        user = db.query(User).filter(
            User.email == "inactive@example.com"
        ).first()

        assert user is not None
        user.is_active = False
        db.commit()

    response = test_client.post(
        "/login",
        json={
            "email": "inactive@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Account is inactive"
