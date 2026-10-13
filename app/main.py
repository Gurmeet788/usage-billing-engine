
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field

from app.database import get_db
from app.models import Tenant, UsageEvent, Plan 

from sqlalchemy import func

app = FastAPI()

class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    plan_id: int | None = Field(default=None, gt=0)


class TenantResponse(BaseModel):
    id: int
    name: str
    plan_id: int | None

    model_config = ConfigDict(from_attributes=True)

class UsageCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=50)
    quantity: int = Field(gt=0)


class UsageSummaryItem(BaseModel):
    event_type: str
    total_quantity: int


class UsageResponse(BaseModel):
    id: int
    tenant_id: int
    event_type: str
    quantity: int

class PlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    monthly_price: int = Field(ge=0)
    included_requests: int = Field(ge=0)


class PlanResponse(BaseModel):
    id: int
    name: str
    monthly_price: int
    included_requests: int

class PlanAssignment(BaseModel):
    plan_id: int = Field(gt=0)


class PlanAssignmentResponse(BaseModel):
    tenant_id: int
    plan_id: int
    plan_name: str


@app.post("/tenants", response_model=TenantResponse)
def create_tenant(
    tenant_data: TenantCreate,
    db: Session = Depends(get_db)
):
    if tenant_data.plan_id is not None:
        plan = db.get(Plan, tenant_data.plan_id)

        if plan is None:
            raise HTTPException(
                status_code=404,
                detail="Plan not found"
            )

    tenant = Tenant(
        name=tenant_data.name,
        plan_id=tenant_data.plan_id
    )

    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    return tenant
@app.get("/tenants", response_model=list[TenantResponse])
def get_tenants(db: Session = Depends(get_db)):
    tenants = db.query(Tenant).all()
    return tenants

@app.post(
    "/tenants/{tenant_id}/usage",
    response_model=UsageResponse
)
def record_usage(
    tenant_id: int,
    usage_data: UsageCreate,
    db: Session = Depends(get_db)
):
    tenant = db.get(Tenant, tenant_id)

    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found"
        )

    usage = UsageEvent(
        tenant_id=tenant_id,
        event_type=usage_data.event_type,
        quantity=usage_data.quantity
    )

    db.add(usage)
    db.commit()
    db.refresh(usage)

    return usage    


@app.get(
    "/tenants/{tenant_id}/usage/summary",
    response_model=list[UsageSummaryItem]
)
def get_usage_summary(
    tenant_id: int,
    db: Session = Depends(get_db)
):
    tenant = db.get(Tenant, tenant_id)

    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found"
        )

    summary = (
        db.query(
            UsageEvent.event_type,
            func.sum(UsageEvent.quantity).label("total_quantity")
        )
        .filter(UsageEvent.tenant_id == tenant_id)
        .group_by(UsageEvent.event_type)
        .all()
    )

    return [
        {
            "event_type": event_type,
            "total_quantity": total_quantity
        }
        for event_type, total_quantity in summary
    ]


@app.post("/plans", response_model=PlanResponse)
def create_plan(
    plan_data: PlanCreate,
    db: Session = Depends(get_db)
):
    plan = Plan(
        name=plan_data.name,
        monthly_price=plan_data.monthly_price,
        included_requests=plan_data.included_requests
    )

    db.add(plan)
    db.commit()
    db.refresh(plan)

    return plan

@app.patch("/tenants/{tenant_id}/plan")
def assign_plan(
    tenant_id: int,
    assignment: PlanAssignment,
    db: Session = Depends(get_db)
):
    tenant = db.get(Tenant, tenant_id)

    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found"
        )

    plan = db.get(Plan, assignment.plan_id)

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Plan not found"
        )

    tenant.plan_id = plan.id
    db.commit()
    db.refresh(tenant)

    return {
        "tenant_id": tenant.id,
        "plan_id": plan.id,
        "plan_name": plan.name
    }