# ShopFlow BD

F-commerce order & delivery management platform for Bangladeshi Facebook/Instagram sellers.

Manage orders, customers, COD, courier deliveries, returns and profit from one dashboard.
Full specification: [docs/PRD.md](docs/PRD.md) · [PDF](docs/ShopFlow_BD_PRD.pdf)

---

## Status

**Phases 1–2 complete.** Backend foundation, catalog and customers are done.

| Phase | Scope | State |
|---|---|---|
| 1 | Auth, stores, staff roles, tenancy | Done |
| 2 | Products, variants, stock, customers | Done |
| 3 | Orders & status state machine | Not started |
| 4 | Couriers & shipments | Not started |
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
│   │   └── customers/       customers, addresses, risk scoring
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
```

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
