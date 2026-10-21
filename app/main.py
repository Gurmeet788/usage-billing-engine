
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field

from app.database import get_db
from app.models import Tenant, UsageEvent, Plan 

from sqlalchemy import func

from pwdlib import PasswordHash
from app.models import User

import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import InvalidTokenError

app = FastAPI()

password_hash = PasswordHash.recommended()

load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is missing from .env")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

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

class UserCreate(BaseModel):
    email: str 
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: int
    tenant_id: int
    email: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)    


class LoginRequest(BaseModel):
    email: str
    password: str

class TenantRegister(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str
    password: str = Field(min_length=8, max_length=128) 
    
       

def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "iat": now,
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )   


security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

        user_id = payload.get("sub")

        if user_id is None:
            raise InvalidTokenError("Missing user ID")

        user = db.get(User, int(user_id))

    except (InvalidTokenError, ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return user   



def get_tenant_owner(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the owner can perform this action"
        )
    return current_user 

def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only platform admins can perform this action"
        )

    return current_user   

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
def get_tenants(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tenants = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).all()
    return tenants

@app.post(
    "/tenants/{tenant_id}/usage",
    response_model=UsageResponse
)
def record_usage(
    tenant_id: int,
    usage_data: UsageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot access this tenant"
        )
    
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot access this tenant"
        )
        
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    if plan_data.name is not None:
        plan = db.query(Plan).filter(Plan.name == plan_data.name).first()
        if plan is not None:
            raise HTTPException(
                status_code=400,
                detail="Plan name already exists"
            )
    if plan_data.monthly_price < 0:
        raise HTTPException(
            status_code=400,
            detail="Monthly price cannot be negative"
        )
    if plan_data.included_requests < 0:
        raise HTTPException(
            status_code=400,
            detail="Included requests cannot be negative"
        )  

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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_tenant_owner)
):
    tenant = db.get(Tenant, tenant_id)

    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found"
        )

    if tenant.id != current_user.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot modify another tenant's plan"
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


@app.get("/plans", response_model=list[PlanResponse])
def get_plans(db: Session = Depends(get_db)):
    plans = db.query(Plan).all()
    return plans    


@app.post(
    "/tenants/{tenant_id}/users",
    response_model=UserResponse,
    status_code=201
)
def register_user(
    tenant_id: int,
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_tenant_owner)
):
    tenant = db.get(Tenant, tenant_id)

    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found"
        )

    if tenant.id != current_user.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot modify another tenant"
        )    

    existing_user = (
        db.query(User)
        .filter(User.email == user_data.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already registered"
        )

    hashed_password = password_hash.hash(user_data.password)

    user = User(
        tenant_id=tenant_id,
        email=user_data.email,
        hashed_password=hashed_password
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user

@app.post("/login")
def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = (
        db.query(User)
        .filter(User.email == login_data.email)
        .first()
    )

    if user is None or not password_hash.verify(
        login_data.password,
        user.hashed_password
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account is inactive"
        )

    access_token = create_access_token(user)

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }  

@app.post("/register", response_model=UserResponse, status_code=201)
def register_tenant(
    data: TenantRegister,
    db: Session = Depends(get_db)
):
    existing_user = (
        db.query(User)
        .filter(User.email == data.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already registered"
        )

    tenant = Tenant(name=data.name)
    db.add(tenant)
    db.flush()

    user = User(
        tenant_id=tenant.id,
        email=data.email,
        hashed_password=password_hash.hash(data.password),
        role="owner"
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@app.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user)
):
    return current_user      
