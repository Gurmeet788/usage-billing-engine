
import pytest

from app.main import create_access_token
from app.models import Tenant, Plan, User, UsageEvent


@pytest.mark.parametrize(
    ("used_requests", "expected_extra"),
    [
        (0, 0),       # Zero usage
        (900, 0),     # Below the limit
        (1000, 0),    # Exactly at the limit
        (1200, 200),  # Above the limit
    ],
)
def test_billing_calculation(client, used_requests, expected_extra):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        plan = Plan(
            name="Test Plan",
            monthly_price=15000,
            included_requests=1000,
            overage_rate=1,
        )
        db.add(plan)
        db.flush()

        tenant = Tenant(name="Test Company", plan_id=plan.id)
        db.add(tenant)
        db.flush()

        user = User(
            tenant_id=tenant.id,
            email=f"user{used_requests}@example.com",
            hashed_password="test-password-hash",
            role="member",
            is_active=True,
        )
        db.add(user)
        db.flush()

        if used_requests > 0:
            db.add(
                UsageEvent(
                    tenant_id=tenant.id,
                    event_type="api_request",
                    quantity=used_requests,
                )
            )

        db.commit()

        tenant_id = tenant.id
        token = create_access_token(user)

    response = test_client.get(
        f"/tenants/{tenant_id}/billing",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total_requests"] == used_requests
    assert data["extra_requests"] == expected_extra
    assert data["overage_charge"] == expected_extra
    assert data["total_bill"] == 15000 + expected_extra


def test_cannot_access_another_tenants_billing(client):
    test_client, TestingSessionLocal = client

    with TestingSessionLocal() as db:
        plan = Plan(
            name="Access Test Plan",
            monthly_price=15000,
            included_requests=1000,
            overage_rate=1,
        )
        db.add(plan)
        db.flush()

        tenant1 = Tenant(name="Company One", plan_id=plan.id)
        tenant2 = Tenant(name="Company Two", plan_id=plan.id)
        db.add_all([tenant1, tenant2])
        db.flush()

        user = User(
            tenant_id=tenant1.id,
            email="owner@example.com",
            hashed_password="test-password-hash",
            role="owner",
            is_active=True,
        )
        db.add(user)
        db.commit()

        other_tenant_id = tenant2.id
        token = create_access_token(user)

    response = test_client.get(
        f"/tenants/{other_tenant_id}/billing",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
