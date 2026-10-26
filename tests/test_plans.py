
from app.models import Tenant, User, Plan
from app.main import create_access_token


def create_test_user(db, name, role="owner"):
    tenant = Tenant(name=name)
    db.add(tenant)
    db.flush()

    user = User(
        tenant_id=tenant.id,
        email=f"{name.lower().replace(' ', '')}@example.com",
        hashed_password="test-password-hash",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()

    token = create_access_token(user)

    return tenant, user, token


def create_test_plan(db, name="Basic"):
    plan = Plan(
        name=name,
        monthly_price=15000,
        included_requests=1000,
        overage_rate=1,
    )
    db.add(plan)
    db.flush()
    return plan


def test_create_plan_as_admin(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, admin, token = create_test_user(
            db, "Platform Admin", role="admin"
        )
        db.commit()

    response = test_client.post(
        "/plans",
        json={
            "name": "Premium",
            "monthly_price": 25000,
            "included_requests": 5000,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Premium"
    assert response.json()["monthly_price"] == 25000
    assert response.json()["included_requests"] == 5000


def test_non_admin_cannot_create_plan(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, user, token = create_test_user(db, "Regular Owner")
        db.commit()

    response = test_client.post(
        "/plans",
        json={
            "name": "Premium",
            "monthly_price": 25000,
            "included_requests": 5000,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_create_plan_with_negative_price_rejected(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, admin, token = create_test_user(
            db, "Admin Negative Price", role="admin"
        )
        db.commit()

    response = test_client.post(
        "/plans",
        json={
            "name": "Invalid Plan",
            "monthly_price": -100,
            "included_requests": 1000,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_duplicate_plan_name_rejected(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, admin, token = create_test_user(
            db, "Admin Duplicate Plan", role="admin"
        )
        create_test_plan(db, name="Basic")
        db.commit()

    response = test_client.post(
        "/plans",
        json={
            "name": "Basic",
            "monthly_price": 20000,
            "included_requests": 2000,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400


def test_list_plans(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        create_test_plan(db, name="Basic")
        create_test_plan(db, name="Premium")
        db.commit()

    response = test_client.get("/plans")

    assert response.status_code == 200

    plan_names = [plan["name"] for plan in response.json()]

    assert "Basic" in plan_names
    assert "Premium" in plan_names


def test_assign_plan_success(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, owner, token = create_test_user(
            db, "Assignment Company"
        )
        plan = create_test_plan(db, name="Premium")
        tenant_id = tenant.id
        plan_id = plan.id
        db.commit()

    response = test_client.patch(
        f"/tenants/{tenant_id}/plan",
        json={"plan_id": plan_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == tenant_id
    assert response.json()["plan_id"] == plan_id
    assert response.json()["plan_name"] == "Premium"


def test_assign_nonexistent_plan_returns_404(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, owner, token = create_test_user(
            db, "Missing Plan Company"
        )
        tenant_id = tenant.id
        db.commit()

    response = test_client.patch(
        f"/tenants/{tenant_id}/plan",
        json={"plan_id": 999999},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_owner_cannot_assign_plan_to_another_tenant(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant_a, owner_a, token_a = create_test_user(
            db, "Company A"
        )
        tenant_b, owner_b, token_b = create_test_user(
            db, "Company B"
        )
        plan = create_test_plan(db, name="Shared Plan")

        tenant_b_id = tenant_b.id
        plan_id = plan.id
        db.commit()

    response = test_client.patch(
        f"/tenants/{tenant_b_id}/plan",
        json={"plan_id": plan_id},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 403


def test_assign_plan_to_nonexistent_tenant_returns_404(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, owner, token = create_test_user(
            db, "Missing Tenant Company"
        )
        plan = create_test_plan(db)
        plan_id = plan.id
        db.commit()

    response = test_client.patch(
        "/tenants/999999/plan",
        json={"plan_id": plan_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_assign_plan_without_token_returns_401(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, owner, token = create_test_user(
            db, "Unauthenticated Company"
        )
        plan = create_test_plan(db)
        tenant_id = tenant.id
        plan_id = plan.id
        db.commit()

    response = test_client.patch(
        f"/tenants/{tenant_id}/plan",
        json={"plan_id": plan_id},
    )

    assert response.status_code == 401
