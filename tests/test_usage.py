
from app.models import Tenant, User, Plan
from app.main import create_access_token


def create_test_tenant(db, name="Test Company", with_plan=True):
    plan = None

    if with_plan:
        plan = Plan(
            name=f"{name} Plan",
            monthly_price=15000,
            included_requests=1000,
            overage_rate=1,
        )
        db.add(plan)
        db.flush()

    tenant = Tenant(
        name=name,
        plan_id=plan.id if plan else None,
    )
    db.add(tenant)
    db.flush()

    user = User(
        tenant_id=tenant.id,
        email=f"{name.lower().replace(' ', '')}@example.com",
        hashed_password="test-password-hash",
        role="owner",
        is_active=True,
    )
    db.add(user)
    db.flush()

    token = create_access_token(user)

    return tenant, user, token


def test_record_usage_success(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, user, token = create_test_tenant(db)
        tenant_id = tenant.id
        db.commit()

    response = test_client.post(
        f"/tenants/{tenant_id}/usage",
        json={
            "event_type": "api_request",
            "quantity": 100,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["event_type"] == "api_request"
    assert response.json()["quantity"] == 100


def test_record_usage_zero_quantity_rejected(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, user, token = create_test_tenant(db)
        tenant_id = tenant.id
        db.commit()

    response = test_client.post(
        f"/tenants/{tenant_id}/usage",
        json={
            "event_type": "api_request",
            "quantity": 0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_record_usage_negative_quantity_rejected(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, user, token = create_test_tenant(db)
        tenant_id = tenant.id
        db.commit()

    response = test_client.post(
        f"/tenants/{tenant_id}/usage",
        json={
            "event_type": "api_request",
            "quantity": -5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_cannot_record_usage_for_another_tenant(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant_a, user_a, token_a = create_test_tenant(db, "Company A")
        tenant_b, user_b, token_b = create_test_tenant(db, "Company B")

        tenant_b_id = tenant_b.id
        db.commit()

    response = test_client.post(
        f"/tenants/{tenant_b_id}/usage",
        json={
            "event_type": "api_request",
            "quantity": 50,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 403


def test_record_usage_for_nonexistent_tenant(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, user, token = create_test_tenant(db)
        db.commit()

    response = test_client.post(
        "/tenants/999999/usage",
        json={
            "event_type": "api_request",
            "quantity": 50,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_usage_summary_returns_correct_totals(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, user, token = create_test_tenant(db)
        tenant_id = tenant.id
        db.commit()

    headers = {"Authorization": f"Bearer {token}"}

    first_response = test_client.post(
        f"/tenants/{tenant_id}/usage",
        json={"event_type": "api_request", "quantity": 100},
        headers=headers,
    )

    second_response = test_client.post(
        f"/tenants/{tenant_id}/usage",
        json={"event_type": "api_request", "quantity": 50},
        headers=headers,
    )

    third_response = test_client.post(
        f"/tenants/{tenant_id}/usage",
        json={"event_type": "report_generated", "quantity": 3},
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert third_response.status_code == 200

    summary_response = test_client.get(
        f"/tenants/{tenant_id}/usage/summary",
        headers=headers,
    )

    assert summary_response.status_code == 200

    summary = {
        item["event_type"]: item["total_quantity"]
        for item in summary_response.json()
    }

    assert summary["api_request"] == 150
    assert summary["report_generated"] == 3


def test_usage_without_token_returns_401(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, user, token = create_test_tenant(db)
        tenant_id = tenant.id
        db.commit()

    response = test_client.post(
        f"/tenants/{tenant_id}/usage",
        json={
            "event_type": "api_request",
            "quantity": 10,
        },
    )

    assert response.status_code == 401
