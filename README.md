# ShopFlow BD

F-commerce order & delivery management platform for Bangladeshi Facebook/Instagram sellers.

Manage orders, customers, COD, courier deliveries, returns and profit from one dashboard.
Full specification: [docs/PRD.md](docs/PRD.md) · [PDF](docs/ShopFlow_BD_PRD.pdf)

---

## Status

**Phases 1–4 complete.** Foundation, catalog, customers, orders and courier delivery are done.

| Phase | Scope | State |
|---|---|---|
| 1 | Auth, stores, staff roles, tenancy | Done |
| 2 | Products, variants, stock, customers | Done |
| 3 | Orders & status state machine | Done |
| 4 | Couriers & shipments | Done |
| 5 | Payments, COD reconciliation, returns | Not started |
| 6 | Dashboard & analytics | Not started |
| 7 | Plans & billing | Not started |

---

## Stack

**Backend** — Django 5.1, Django REST Framework, JWT (SimpleJWT), SQLite locally / PostgreSQL in production
**Frontend** — React 18 + JavaScript (ES2022+) + Vite
**Deployment** — Render

No Docker and no Redis: the project targets Render's free tier, where periodic work runs as
Render Cron Jobs invoking management commands rather than as Celery beat tasks.

---

## Local setup

Requires Python 3.12+ and Node 20+.

```bash
# 1. virtual environment
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash)
# .venv\Scripts\activate           # Windows (PowerShell)
# source .venv/bin/activate        # macOS / Linux

# 2. dependencies
pip install -r backend/requirements-dev.txt

# 3. environment file
cd backend
cp .env.example .env
```

Then fill in `.env`. Generate the two keys with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```bash
# 4. database + run
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

| URL | What |
|---|---|
| http://127.0.0.1:8000/api/docs/ | Swagger UI |
| http://127.0.0.1:8000/admin/ | Django admin |
| http://127.0.0.1:8000/healthz/ | Health probe |

---

## Tests

```bash
cd backend
pytest                    # everything
pytest tests/test_tenancy.py   # cross-tenant isolation
pytest --cov=apps --cov-report=term-missing
```

`tests/test_tenancy.py` is the suite that matters most. The PRD rates multi-tenant data
leakage as a Critical risk, so isolation is asserted directly: a seller must never see
another seller's stores, staff, or settings, and a forged `X-Store-Id` header must be
refused.

`tests/test_concurrency.py` skips on SQLite and only runs against PostgreSQL, because
`select_for_update` takes no row lock on SQLite. It proves two simultaneous order
confirmations cannot oversell the same stock. To run it locally you need Postgres:

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname pytest tests/test_concurrency.py
```

Otherwise CI covers it on every push.

## CI

`.github/workflows/ci.yml` runs three jobs on push and pull request to `main`:

| Job | What it checks |
|---|---|
| Lint | `ruff check` |
| Tests (SQLite) | Full suite, plus `makemigrations --check` so a model change without a migration fails the build |
| Tests (PostgreSQL) | Full suite against Postgres 16, including the concurrency suite |

The Postgres job ends with a guard that fails if the concurrency tests report as skipped —
without it a misconfiguration would silently leave stock locking unverified while CI
still showed green.

---

## Layout

```
F-commerce/
├── backend/
│   ├── config/
│   │   ├── settings/        base.py · dev.py · prod.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── apps/
│   │   ├── core/            base models, tenancy mixins, errors, pagination
│   │   ├── accounts/        User, JWT auth, registration
│   │   ├── stores/          Store, memberships, roles, settings, invitations
│   │   ├── catalog/         products, variants, stock items, stock ledger
│   │   ├── customers/       customers, addresses, risk scoring
│   │   ├── orders/          orders, items, status state machine
│   │   ├── couriers/        courier registry, adapters, credential storage
│   │   └── shipments/       shipments, tracking history, sync
│   ├── tests/
│   └── requirements.txt
├── frontend/                React app
└── docs/                    PRD
```

Business logic belongs in a `services.py` per app. Views stay thin, serializers validate,
services own invariants and transactions — so the order state machine (Phase 3) stays
testable without HTTP.

---

## Multi-tenancy

A **Store** is the tenant boundary. Every business table carries `store_id`, and access is
determined entirely by **StoreMembership**.

Store resolution for a request:

1. the `X-Store-Id` header, or
2. the caller's single active membership, if they have exactly one

Belonging to several stores without sending the header is ambiguous and is rejected rather
than guessed.

Two rules make this structural rather than a thing each view must remember:

- `StoreScopedMixin` filters every queryset to the resolved store, and returns **nothing**
  when no store resolved — it fails closed.
- A store that isn't yours returns **404**, not 403, so the API never confirms that another
  tenant's record exists.

### Roles

Owner · Manager · Order Staff · Delivery Staff · Accountant

Capabilities live in one table in `apps/stores/permissions.py`. Views declare the capability
they need and never test role strings inline, so adding a role means editing one dict.
`tests/test_permissions.py` asserts that table row by row against the PRD.

---

## API

Base path `/api/v1/`. Full schema at `/api/docs/`.

```
POST   /auth/register/            create account, returns tokens
POST   /auth/login/               tokens + store memberships
POST   /auth/refresh/             rotate access token
POST   /auth/logout/              blacklist refresh token
GET    /auth/me/                  current user + stores
POST   /auth/password/change/

GET    /stores/                   stores you belong to
POST   /stores/                   create store (+ owner membership + settings)
GET    /stores/{id}/
PATCH  /stores/{id}/              owner or manager
DELETE /stores/{id}/              owner only, soft delete
GET    /stores/{id}/settings/
PATCH  /stores/{id}/settings/     owner or manager

GET    /stores/staff/             owner only
PATCH  /stores/staff/{id}/        change role
DELETE /stores/staff/{id}/        deactivate membership

GET    /stores/invitations/
POST   /stores/invitations/       invite by email, 72h expiry
DELETE /stores/invitations/{id}/  revoke
POST   /stores/invitations/accept/    public, by token

GET    /stores/my-capabilities/   what the caller may do

GET|POST   /categories/          product categories
GET|POST   /products/            list (search, filter, low_stock) / create
GET|PATCH|DELETE /products/{id}/ detail; delete deactivates
POST   /products/{id}/images/    upload image (max 6)
GET    /products/{id}/movements/ stock ledger for one product
GET    /products/export/         CSV export
POST   /products/import/         CSV import (dry-run unless commit=true)

GET    /stock/                   stock levels, ?low_stock=true
GET    /stock/summary/           totals + low-stock count
GET    /stock/movements/         immutable stock ledger
POST   /stock/receive/           restock
POST   /stock/adjust/            manual adjustment, reason required

GET|POST   /customers/           list (search, risk filter) / create
GET|PATCH  /customers/{id}/      detail with metrics and addresses
GET    /customers/lookup/?phone= order-entry autofill
POST   /customers/{id}/blacklist/
GET|POST   /customers/{id}/addresses/

GET|POST   /orders/              list (search, filters, cursor paging) / create
GET|PATCH  /orders/{id}/         detail; PATCH edits address and notes only
PATCH  /orders/{id}/status/      transition through the state machine
POST   /orders/{id}/confirm/     log a call outcome, confirm or cancel
PATCH  /orders/{id}/items/       change items while Pending or Confirmed
GET    /orders/{id}/history/     status timeline
GET    /orders/stats/            counts by status
POST   /orders/bulk-status/      bulk transition with per-order results
POST   /orders/check-duplicate/  warn before creating a repeat order

GET    /couriers/               available couriers + required credentials
GET|POST   /couriers/store-couriers/   enable a courier for the store
POST   /couriers/store-couriers/{id}/verify/   test stored credentials

POST   /shipments/book/         book one parcel (API or manual)
POST   /shipments/bulk-book/    book many, with per-order results
GET    /shipments/              list, ?in_transit=true, ?cod_outstanding=true
GET    /shipments/{id}/         detail + full tracking history
POST   /shipments/{id}/sync/    force a tracking refresh
POST   /shipments/{id}/status/  record a status by hand (manual couriers)
POST   /shipments/{id}/cost/    record what the courier actually charged
POST   /shipments/{id}/cancel/  cancel the shipment
POST   /webhooks/courier/{code}/   signed courier callback, public
```

## Couriers

Every courier sits behind one adapter interface in `apps/couriers/adapters/`, so adding a
courier touches no order or shipment code. Three ship today:

| Adapter | Booking | Tracking | Webhook |
|---|---|---|---|
| `manual` | Type the consignment id yourself | Update by hand | — |
| `pathao` | API | Polled | Signature header |
| `steadfast` | API | Polled | HMAC-SHA256 |

**Manual mode needs no credentials and works immediately** — book on the courier's own site,
paste the consignment id, and the order still moves and COD is still tracked. API booking
switches on the moment credentials are saved; `GET /couriers/` tells the frontend which
fields each courier requires.

Credentials are encrypted at rest with Fernet (`FIELD_ENCRYPTION_KEY`) and are never
returned by the API. A test asserts this by reading the raw column with SQL.

Courier statuses never reach an order directly. Each adapter maps them onto our own
statuses, and the result is applied only if the state machine allows it — a courier cannot
push an order into an illegal state, and an unrecognised status is recorded in tracking
history without touching the order.

Every outbound call has a timeout, bounded retries with backoff, and a circuit breaker, so
one courier's outage cannot stall booking. If booking fails the order stays Confirmed with
its stock still reserved, so nothing is silently lost.

### Tracking sync without Celery

Render's free tier has no Redis or background workers, so polling runs as a management
command driven by a Render Cron Job:

```bash
python manage.py sync_tracking --limit 200
```

The poll interval widens with shipment age (15 min for the first 2 days, 2 h to a week,
12 h to a month), and a shipment that fails 10 times in a row is dropped from the rotation.

## Order lifecycle

```
Pending ──► Confirmed ──► Processing ──► Ready to Ship ──► Shipped ──► Out for Delivery ──► Delivered
   │            │              │               │               │              │                │
   │            └──────────────┴───────────────┘               └──────────────┴────► Returned ◄┘
   │                           │
   └───────────────────────────┴────► Cancelled        Pending/Confirmed ◄──► On Hold
```

Transitions are enforced in `apps/orders/services.py`; anything not in the map returns
`409 INVALID_TRANSITION` listing what is allowed. Every change writes an append-only
`OrderStatusHistory` row.

Stock effects are tied to the transition, not to a separate call:

| Transition | Effect |
|---|---|
| → Confirmed | Reserves stock; fails with `409 INSUFFICIENT_STOCK` if short |
| → Cancelled / On Hold | Releases the reservation |
| → Shipped | Converts the reservation into a real decrement of `on_hand` |
| → Delivered | Updates the customer's delivered count and lifetime value |
| → Returned | Updates return count and may escalate the customer's risk level |

Item prices, costs and product names are **snapshotted** onto `OrderItem` at creation, so
editing a product later never rewrites past orders.

Errors use one envelope throughout:

```json
{ "error": { "code": "INVALID_TRANSITION", "message": "...", "details": {} } }
```

Codes are stable and part of the contract.

---

## Conventions

- Money is `DecimalField(max_digits=12, decimal_places=2)`. Never a float, anywhere.
- Phone numbers normalise to `+8801XXXXXXXXX` on save, so lookup-by-phone is reliable.
- History tables are append-only; records needing an audit trail are soft-deleted.
- Order numbers come from an atomic per-store counter, never `COUNT(*) + 1`.
- Secrets live in `.env` (gitignored) and in Render's environment settings. Never committed.
