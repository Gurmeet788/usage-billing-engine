
from app.main import create_access_token
from app.models import Tenant, User, Plan, UsageEvent

def create_billing_setup(
    db,
    name,
    included_requests=1000,
    monthly_price=15000,
    overage_rate=1,
):
    plan = Plan(
        name=f"{name} Plan",
        monthly_price=monthly_price,
        included_requests=included_requests,
        overage_rate=overage_rate,
    )
    db.add(plan)
    db.flush()

    tenant = Tenant(name=name, plan_id=plan.id)
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

    return tenant, token


def test_billing_with_zero_usage(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, token = create_billing_setup(db, "Zero Usage")
        tenant_id = tenant.id
        db.commit()

    response = test_client.get(
        f"/tenants/{tenant_id}/billing",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 0
    assert data["extra_requests"] == 0
    assert data["overage_charge"] == 0
    assert data["total_bill"] == 15000


def test_billing_exactly_at_included_limit(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, token = create_billing_setup(
            db, "Exact Limit", included_requests=1000
        )
        tenant_id = tenant.id
        db.add_all([
            __import__("app.models", fromlist=["UsageEvent"]).UsageEvent(
                tenant_id=tenant_id,
                event_type="api_request",
                quantity=600,
            ),
            __import__("app.models", fromlist=["UsageEvent"]).UsageEvent(
                tenant_id=tenant_id,
                event_type="api_request",
                quantity=400,
            ),
        ])
        db.commit()

    response = test_client.get(
        f"/tenants/{tenant_id}/billing",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 1000
    assert data["extra_requests"] == 0
    assert data["overage_charge"] == 0
    assert data["total_bill"] == 15000


def test_billing_one_request_over_limit(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, token = create_billing_setup(
            db,
            "One Over",
            included_requests=1000,
            overage_rate=1,
        )
        tenant_id = tenant.id
        from app.models import UsageEvent
        db.add(UsageEvent(
            tenant_id=tenant_id,
            event_type="api_request",
            quantity=1001,
        ))
        db.commit()

    response = test_client.get(
        f"/tenants/{tenant_id}/billing",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 1001
    assert data["extra_requests"] == 1
    assert data["overage_charge"] == 1
    assert data["total_bill"] == 15001


def test_billing_multiple_requests_over_limit(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, token = create_billing_setup(
            db,
            "Multiple Over",
            included_requests=1000,
            monthly_price=15000,
            overage_rate=2,
        )
        tenant_id = tenant.id
        from app.models import UsageEvent
        db.add(UsageEvent(
            tenant_id=tenant_id,
            event_type="api_request",
            quantity=1200,
        ))
        db.commit()

    response = test_client.get(
        f"/tenants/{tenant_id}/billing",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 1200
    assert data["extra_requests"] == 200
    assert data["overage_charge"] == 400
    assert data["total_bill"] == 15400
