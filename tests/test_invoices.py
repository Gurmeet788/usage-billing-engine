
from app.main import create_access_token
from app.models import Tenant, Plan, User, UsageEvent, Invoice


def create_test_tenant(db, name="Test Company", with_plan=True):
    """Create a test tenant and owner, and generate an access token."""

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

    # Generate the token while the user is still attached to the session.
    token = create_access_token(user)

    return tenant, user, token


def test_create_invoice_success(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, user, token = create_test_tenant(db)

        db.add(
            UsageEvent(
                tenant_id=tenant.id,
                event_type="api_request",
                quantity=1200,
            )
        )
        db.commit()

        tenant_id = tenant.id

    response = test_client.post(
        f"/tenants/{tenant_id}/invoices",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201

    data = response.json()
    assert data["tenant_id"] == tenant_id
    assert data["plan_price"] == 15000
    assert data["overage_charge"] == 200
    assert data["total_amount"] == 15200
    assert data["status"] == "pending"


def test_duplicate_invoice_returns_conflict(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, user, token = create_test_tenant(db)
        tenant_id = tenant.id
        db.commit()

    headers = {"Authorization": f"Bearer {token}"}
    url = f"/tenants/{tenant_id}/invoices"

    first_response = test_client.post(url, headers=headers)
    second_response = test_client.post(url, headers=headers)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "An invoice already exists for this billing period"
    )


def test_invoice_without_plan_returns_bad_request(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant, user, token = create_test_tenant(
            db,
            name="No Plan Company",
            with_plan=False,
        )
        tenant_id = tenant.id
        db.commit()

    response = test_client.post(
        f"/tenants/{tenant_id}/invoices",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Tenant has no assigned plan"


def test_cannot_create_invoice_for_another_tenant(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        tenant1, user, token = create_test_tenant(
            db, "Company One"
        )
        tenant2, _, _ = create_test_tenant(
            db, "Company Two"
        )

        other_tenant_id = tenant2.id
        db.commit()

    response = test_client.post(
        f"/tenants/{other_tenant_id}/invoices",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_create_invoice_without_token_returns_401(client):
    test_client, _ = client

    response = test_client.post("/tenants/1/invoices")

    assert response.status_code == 401
