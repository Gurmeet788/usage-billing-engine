# Usage & Billing Engine

A multi-tenant usage-based billing platform and metering API built with **FastAPI**, **SQLAlchemy**, **PostgreSQL**, and **Safepay Payment Gateway**.

Designed for SaaS platforms that charge customers based on a recurring subscription tier combined with metered resource consumption (overage fees).

---

## Table of Contents

- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Database Schema (ERD)](#database-schema-erd)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Database Migrations](#database-migrations)
  - [Creating a Platform Admin](#creating-a-platform-admin)
  - [Running the API Server](#running-the-api-server)
- [API Reference](#api-reference)
  - [Authentication & Users](#authentication--users)
  - [Tenants](#tenants)
  - [Plans & Subscriptions](#plans--subscriptions)
  - [Usage Metering](#usage-metering)
  - [Billing & Invoicing](#billing--invoicing)
  - [Safepay Payments & Webhooks](#safepay-payments--webhooks)
- [Billing & Overage Formula](#billing--overage-formula)
- [Safepay Payment Flow](#safepay-payment-flow)
- [Running Automated Tests](#running-automated-tests)
- [License](#license)

---

## Key Features

- **Multi-Tenant Isolation**: Complete isolation of customer accounts, users, usage events, and invoices.
- **Role-Based Access Control (RBAC)**:
  - `admin`: Platform administrator capable of managing plans and system resources.
  - `owner`: Tenant account owner capable of managing subscription plans and inviting team members.
  - `member`: Standard tenant member capable of recording and querying usage.
- **JWT Authentication & Password Security**: Secure JWT bearer tokens (HS256) and modern Argon2 password hashing via `pwdlib`.
- **Metered Usage Tracking**: Real-time event ingestion and aggregation per tenant and event type.
- **Dynamic Overage Calculation**: Automated computation of included requests, extra usage, overage unit rates, and total bill.
- **Invoice Lifecycle Management**: Idempotent monthly billing periods protected by database unique constraints (`uq_invoice_tenant_billing_period`).
- **Safepay Payment Gateway Integration**:
  - Hosted checkout session generation with short-lived client passport tokens (`tbt`).
  - Webhook listener with HMAC-SHA256 signature verification (`X-SFPY-Signature`) for automatic invoice reconciliation (`paid`).
- **Database Migrations with Alembic**: Fully revision-controlled database schema migrations.
- **Comprehensive Test Suite**: Isolated testing with in-memory SQLite and FastAPI TestClient (100% test pass rate).

---

## System Architecture

```mermaid
graph TD
    Client["Client / Frontend / SDK"]
    
    subgraph FastAPI Application
        Auth["JWT Auth & RBAC Middleware"]
        TenantRouter["Tenants & Users"]
        PlanRouter["Plans Management"]
        UsageRouter["Usage Metering"]
        BillingRouter["Billing & Invoices"]
        SafepayService["Safepay Service (Tracker / Checkout)"]
        WebhookHandler["Safepay Webhook Listener"]
    end

    subgraph Persistence Layer
        DB[("PostgreSQL Database")]
        Alembic["Alembic Migrations"]
    end

    subgraph External Services
        SafepayAPI["Safepay API (Sandbox / Prod)"]
    end

    Client -->|Bearer Token HTTP Requests| Auth
    Auth --> TenantRouter
    Auth --> PlanRouter
    Auth --> UsageRouter
    Auth --> BillingRouter
    
    TenantRouter --> DB
    PlanRouter --> DB
    UsageRouter --> DB
    BillingRouter --> DB
    
    BillingRouter -->|Create Tracker| SafepayService
    SafepayService -->|Init Order| SafepayAPI
    SafepayAPI -->|Webhook Signature & Payload| WebhookHandler
    WebhookHandler -->|Update Invoice Status: Paid| DB
```

---

## Database Schema (ERD)

```mermaid
erDiagram
    tenants ||--o{ users : "has"
    tenants ||--o{ usage_events : "incurs"
    tenants ||--o{ invoices : "billed via"
    plans ||--o{ tenants : "assigned to"

    tenants {
        int id PK
        string name
        int plan_id FK "nullable"
    }

    plans {
        int id PK
        string name "UK"
        int monthly_price
        int included_requests
        int overage_rate
    }

    users {
        int id PK
        int tenant_id FK
        string email "UK, indexed"
        string role "admin | owner | member"
        string hashed_password
        boolean is_active
    }

    usage_events {
        int id PK
        int tenant_id FK
        string event_type
        int quantity
        datetime created_at
    }

    invoices {
        int id PK
        int tenant_id FK
        datetime billing_period_start
        datetime billing_period_end
        int plan_price
        int overage_charge
        int total_amount
        string status "pending | paid"
        string safepay_tracker "nullable"
        datetime created_at
    }
```

---

## Tech Stack

| Technology | Purpose |
|---|---|
| **Python 3.11+ / 3.13** | Core backend language |
| **FastAPI** | High-performance asynchronous REST API framework |
| **SQLAlchemy 2.0** | Declarative ORM and database abstraction layer |
| **PostgreSQL** | Primary relational database (supports local, AWS RDS, Supabase) |
| **Alembic** | Schema migrations and versioning |
| **PyJWT** | JSON Web Token encoding, decoding, and verification |
| **pwdlib (Argon2)** | Secure, memory-hard password hashing |
| **HTTPX** | Asynchronous / synchronous HTTP client for Safepay gateway integration |
| **Safepay API** | Digital payment gateway and hosted checkout integration |
| **Pytest & TestClient** | Unit, integration, and edge-case test suite |

---

## Project Structure

```text
usage-billing-engine/
│
├── alembic/                       # Alembic database migration scripts
│   ├── env.py                     # Alembic configuration & model target metadata
│   ├── script.py.mako             # Migration template
│   └── versions/                  # Revision files (11 tracked versions)
├── app/
│   ├── __init__.py
│   ├── database.py                # Database engine & SessionLocal dependency
│   ├── main.py                    # FastAPI routes, schemas, and RBAC dependencies
│   ├── models.py                  # SQLAlchemy declarative ORM models
│   └── safepay_service.py         # Safepay API, passport tokens, and HMAC verification
│
├── tests/                         # Pytest test suite
│   ├── conftest.py                # In-memory SQLite fixture and test dependency overrides
│   ├── test_auth.py               # Authentication, token validation, user registration
│   ├── test_billing.py            # Billing calculation tests
│   ├── test_billing_edge_cases.py # Overage limits, zero usage, plan switching
│   ├── test_invoices.py           # Invoicing generation and uniqueness constraints
│   ├── test_plans.py              # Plan creation, constraints, role checks
│   └── test_usage.py              # Usage event ingestion and aggregation
│
├── .env.example                   # Environment configuration template
├── alembic.ini                    # Alembic settings
├── create_admin.py                # CLI script to bootstrap a platform admin account
├── pytest.ini                     # Pytest configuration
├── requirements.txt               # Locked project dependencies
└── README.md                      # Documentation
```

---

## Getting Started

### Prerequisites

- **Python**: Version 3.11 or later
- **PostgreSQL**: Running instance (Local, Docker, or Cloud such as Neon / Supabase)
- **Safepay Merchant Account**: For sandbox testing keys ([Safepay Sandbox](https://sandbox.api.getsafepay.com))

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/<your-username>/usage-billing-engine.git
   cd usage-billing-engine
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # On macOS/Linux
   python3 -m venv venv
   source venv/bin/activate

   # On Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### Environment Variables

Copy `.env.example` to `.env` and fill in the required variables:

```bash
cp .env.example .env
```

| Variable | Description | Example / Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg2://user:password@localhost:5432/usage_billing_db` |
| `JWT_SECRET_KEY` | Secret key for signing JWT tokens | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SAFEPAY_ENV` | Gateway environment | `sandbox` or `production` |
| `SAFEPAY_BASE_URL` | Safepay API URL | `https://sandbox.api.getsafepay.com` |
| `SAFEPAY_API_KEY` | Public key starting with `sec_` | `sec_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `SAFEPAY_SECRET_KEY` | Merchant secret key (hex string) | Safepay Dashboard -> Developer |
| `SAFEPAY_WEBHOOK_SECRET`| Webhook verification secret | Safepay Dashboard -> Developer -> Webhooks |
| `SAFEPAY_CURRENCY` | Default currency ISO code | `PKR` |

### Database Migrations

Apply all existing schema migrations using Alembic:

```bash
alembic upgrade head
```

To create a new migration after editing `app/models.py`:
```bash
alembic revision --autogenerate -m "describe_changes"
alembic upgrade head
```

### Creating a Platform Admin

A CLI script is provided to create the root platform administrator:

```bash
python create_admin.py
```
Follow the interactive prompt to set the admin email and password. This creates a dedicated `Platform Administration` tenant and an active user with the `admin` role.

### Running the API Server

Start the local development server with Uvicorn:

```bash
uvicorn app.main:app --reload --port 8000
```

- **Interactive API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative Documentation (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## API Reference

All protected endpoints require an `Authorization: Bearer <token>` header obtained from `/login`.

### Authentication & Users

| Method | Endpoint | Auth Required | Role | Description |
|---|---|---|---|---|
| `POST` | `/register` | None | Public | Register a new tenant organization with an `owner` account. |
| `POST` | `/login` | None | Public | Authenticate user credentials and receive a JWT access token. |
| `GET` | `/me` | Bearer Token | Any | Retrieve the current authenticated user's profile and tenant ID. |
| `POST` | `/tenants/{tenant_id}/users` | Bearer Token | `owner` | Register a new member account under the owner's tenant. |

### Tenants

| Method | Endpoint | Auth Required | Role | Description |
|---|---|---|---|---|
| `POST` | `/tenants` | None | Public | Create a standalone tenant (optionally pre-assigned to a plan). |
| `GET` | `/tenants` | Bearer Token | Any | List tenant records associated with the authenticated user. |

### Plans & Subscriptions

| Method | Endpoint | Auth Required | Role | Description |
|---|---|---|---|---|
| `POST` | `/plans` | Bearer Token | `admin` | Create a new subscription tier with base price & included units. |
| `GET` | `/plans` | None | Public | List all available subscription plans. |
| `PATCH` | `/tenants/{tenant_id}/plan` | Bearer Token | `owner` | Assign or switch the subscription plan for the tenant. |

### Usage Metering

| Method | Endpoint | Auth Required | Role | Description |
|---|---|---|---|---|
| `POST` | `/tenants/{tenant_id}/usage` | Bearer Token | Member / Owner | Ingest a metered usage event (`event_type`, `quantity`). |
| `GET` | `/tenants/{tenant_id}/usage/summary` | Bearer Token | Member / Owner | Aggregate total usage grouped by `event_type`. |

### Billing & Invoicing

| Method | Endpoint | Auth Required | Role | Description |
|---|---|---|---|---|
| `GET` | `/tenants/{tenant_id}/billing` | Bearer Token | Member / Owner | Calculate the current real-time billing breakdown and overage charges. |
| `POST` | `/tenants/{tenant_id}/invoices` | Bearer Token | Member / Owner | Generate the monthly invoice for the current calendar period. |

### Safepay Payments & Webhooks

| Method | Endpoint | Auth Required | Role | Description |
|---|---|---|---|---|
| `POST` | `/tenants/{tenant_id}/invoices/{invoice_id}/pay` | Bearer Token | Member / Owner | Initialize a Safepay hosted checkout session and receive redirect URL. |
| `POST` | `/safepay/webhook` | Webhook Signature | Safepay Server | Receives payment callbacks, verifies HMAC signature, and marks invoice `paid`. |

---

## Billing & Overage Formula

The engine dynamically computes charges as follows:

$$\text{extra\_requests} = \max(0, \text{total\_requests} - \text{plan.included\_requests})$$

$$\text{overage\_charge} = \text{extra\_requests} \times \text{plan.overage\_rate}$$

$$\text{total\_bill} = \text{plan.monthly\_price} + \text{overage\_charge}$$

### Example:
- **Plan**: Growth Plan
- **Monthly Base Price**: 5,000 PKR
- **Included Requests**: 100,000
- **Overage Rate**: 2 PKR per extra request
- **Recorded Total Usage**: 125,000 requests

$$\text{Extra Requests} = 125,000 - 100,000 = 25,000$$
$$\text{Overage Charge} = 25,000 \times 2 = 50,000 \text{ PKR}$$
$$\text{Total Bill} = 5,000 + 50,000 = 55,000 \text{ PKR}$$

---

## Safepay Payment Flow

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Tenant User
    participant API as FastAPI Engine
    participant Safepay as Safepay Gateway
    participant DB as Database

    Customer->>API: POST /tenants/{tenant_id}/invoices/{id}/pay
    API->>Safepay: Request client passport token (tbt)
    Safepay-->>API: Return tbt
    API->>Safepay: POST /order/v1/init (amount, currency)
    Safepay-->>API: Return tracker token & checkout URL
    API->>DB: Save safepay_tracker on Invoice record
    API-->>Customer: Return checkout_url
    Customer->>Safepay: Redirect to hosted checkout page & complete payment
    Safepay->>API: POST /safepay/webhook (event: payment:created, status: PAID)
    Note over API: Verify X-SFPY-Signature via HMAC-SHA256
    API->>DB: Update invoice status to "paid"
    API-->>Safepay: 200 OK {"received": true}
```

---

## Running Automated Tests

The test suite uses **Pytest** with an in-memory SQLite database and isolated dependency injection overrides. No external database or credentials are required for tests.

Execute the full suite:

```bash
python -m pytest -v
```

To run a specific test suite:
```bash
python -m pytest tests/test_billing.py -v
python -m pytest tests/test_invoices.py -v
python -m pytest tests/test_plans.py -v
```

---

## Security Best Practices

- **Never commit `.env`**: Always keep credentials out of version control.
- **Tenant Scope Enforcement**: All protected routes cross-check `current_user.tenant_id == tenant_id` to guarantee zero cross-tenant data leakage.
- **Webhook Verification**: The `/safepay/webhook` endpoint validates payloads against `SAFEPAY_WEBHOOK_SECRET` using cryptographic constant-time comparison to avoid timing attacks.
