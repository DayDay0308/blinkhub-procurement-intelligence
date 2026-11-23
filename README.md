# BlinkHub Procurement Intelligence & Risk Engine

A working prototype for the **BlinkHub Procurement Innovation Challenge** (MICS scenario). It gives Mzansi Infrastructure & Community Services one trustworthy view of the procure-to-pay chain: where the money goes, which invoices are stuck and why, and which transactions need investigating.

> **All data is fictional.** The seed reproduces the case study's sample records exactly; any expansion is synthetic and labelled. Nothing here represents MICS's actual performance.

![CI](https://github.com/DayDay0308/blinkhub-procurement-intelligence/actions/workflows/ci.yml/badge.svg)

## Problems addressed

| Case study problem | What this solves |
|---|---|
| 3. Where is the money? | Spend by department, supplier, category and province; SMME share; concentration |
| 4. The invoice that never gets paid | Invoice ageing, 30-day SLA ladder, accountable approver, supplier self-service status |
| 6. Something doesn't look right | Explainable risk flags for investigation (never automatic accusations) |

Full reasoning: [docs/architecture.md](docs/architecture.md) · Data model: [docs/erd.md](docs/erd.md)

## Quick start (Docker)

Requires Docker Desktop.

```bash
git clone https://github.com/DayDay0308/blinkhub-procurement-intelligence.git
cd blinkhub-procurement-intelligence
cp .env.example .env          # Windows PowerShell: copy .env.example .env
docker compose up --build
```

On first start, the API applies database migrations and loads the case-study data.

| What | Where |
|---|---|
| Interactive API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| PostgreSQL (Power BI, DBeaver) | `localhost:5432`, db `blinkhub`, user/password from `.env` |
| Worker logs (SLA job) | `docker compose logs -f worker` |

### Demo accounts

All demo users share the password `Demo@2026!` (set by `DEMO_PASSWORD`).

| Email | Role | Sees |
|---|---|---|
| `procurement@mics.demo` | Procurement Officer | Suppliers, POs; registers suppliers |
| `finance@mics.demo` | Finance Officer | All invoices |
| `approver@mics.demo` | Approver | Invoices to approve |
| `manager@mics.demo` | Manager | Everything, dashboards |
| `auditor@mics.demo` | Auditor | Read-only everything |
| `admin@mics.demo` | Admin | Users, rules |
| `accounts@ubuntucleaning.demo` | Supplier | **Only Ubuntu Cleaning's** invoices |
| `accounts@thutosupplies.demo` | Supplier | **Only Thuto Supplies'** invoices |

**Try it in Swagger:** click **Authorize**, sign in as `manager@mics.demo`, then call `GET /api/v1/invoices?overdue=true`. Then sign in as `accounts@ubuntucleaning.demo` and call the same endpoint: the supplier only sees its own two invoices.

## Local development (without Docker for the API)

Uses [uv](https://docs.astral.sh/uv/) for the Python virtual environment.

```bash
docker compose up -d db                 # just the database
cd backend
uv sync                                 # creates .venv with all dependencies
uv run alembic upgrade head             # apply migrations
uv run python -m seed.run               # load case-study data (--reset to reload)
uv run uvicorn app.main:app --reload    # http://localhost:8000/docs
```

In VS Code, select the interpreter at `backend/.venv` (Ctrl+Shift+P → *Python: Select Interpreter*).

### Tests and linting

Tests run against a real PostgreSQL database, because many business rules are database constraints.

```bash
cd backend
uv run pytest            # creates and drops its own blinkhub_test database
uv run ruff check .
uv run ruff format .
```

GitHub Actions runs lint, tests and a Docker build on every push.

## What's built so far

### Invoice workflow (Problem 4)

```
Supplier submits (portal) ─┐
Finance captures (email) ──┴─> 3-way match: PO ↔ goods receipt ↔ invoice
        ├─ exceptions ──> EXCEPTION, owned by Finance, with reasons
        │                  (MISSING_PO_REFERENCE, AWAITING_GOODS_RECEIPT,
        │                   AMOUNT_EXCEEDS_PO, EXCEEDS_GOODS_RECEIVED, PO_NOT_APPROVED)
        └─ clean ──> PENDING_APPROVAL, routed to ONE named approver
                         (limit covers amount, same department first, never the PO requester)
                     ├─ APPROVED ──> Finance owns payment ──> PAID (verified bank account)
                     └─ REJECTED (reason required)
Recording a goods receipt automatically re-matches the invoices waiting on that PO.
```

- **Accountability:** every open invoice has a named owner (`current_owner`).
- **Supplier visibility:** suppliers see a timeline of every step, plus notifications when an invoice is approved, rejected or paid.
- **Payment deadlines:** a Celery beat job runs every 15 minutes and alerts as the 30-day terms approach:
  - day 20: the owner is warned
  - day 25: escalated to managers
  - after day 30: breached, and managers and Finance are alerted
  - SMME invoices are tagged **[SMME priority]**
  - re-running the job never sends duplicate alerts
- **Controls:**
  - row locks prevent double approval or double payment
  - only the assigned approver can approve; a manager can override, but must give a reason
  - each approver has an approval limit
  - whoever changed a supplier's bank details can't release a payment to that supplier within 72 hours
  - bank account numbers are encrypted at rest (pgcrypto)

### API endpoints (`/api/v1`)

| Method | Path | Who |
|---|---|---|
| POST | `/auth/login` · GET `/auth/me` | Everyone |
| GET/POST | `/suppliers` · GET `/suppliers/{id}` | Staff (register: Procurement) · suppliers see own |
| GET | `/invoices` (`status`, `overdue`, `assigned_to_me`, `sort`) | Signed in; suppliers scoped to own |
| POST | `/invoices` | Supplier (portal) · Finance (captured email invoice) |
| GET | `/invoices/{id}` · `/invoices/{id}/timeline` | Same scoping |
| POST | `/invoices/{id}/link-po` | Finance, Procurement |
| POST | `/invoices/{id}/approve` · `/reject` | Assigned approver · Manager override |
| POST | `/invoices/{id}/pay` | Finance |
| GET | `/purchase-orders` | Staff |
| POST | `/purchase-orders/{po}/goods-receipts` | Procurement |
| GET | `/notifications` · POST `/notifications/{id}/read` | Signed in |
| POST | `/jobs/sla-check` | Manager, Admin (also runs on schedule) |

### Demo script (Swagger)

1. Sign in as **`accounts@thutosupplies.demo`** and `POST /invoices` with `{"invoice_number": "TS-1001", "po_number": "PO010", "amount": 42000, "invoice_date": "<today>"}`. The result is `EXCEPTION` with the reason `AWAITING_GOODS_RECEIPT`.
2. Submit the same invoice as `ts 1001`. It's blocked with `409`.
3. Sign in as **`procurement@mics.demo`** and `POST /purchase-orders/PO010/goods-receipts` with `{"amount_received": 42000, "received_date": "<today>"}`. The invoice moves to `PENDING_APPROVAL`, owned by Anele (Approver).
4. Sign in as **`approver@mics.demo`**. `GET /invoices?assigned_to_me=true` lists it; `POST /invoices/{id}/approve`.
5. Sign in as **`finance@mics.demo`** and `POST /invoices/{id}/pay`.
6. Back as Thuto, `GET /invoices/{id}/timeline` shows submitted → exception → routed → approved → paid.
7. As **`manager@mics.demo`**, `POST /jobs/sla-check`, then `GET /notifications`. The breached invoices appear, with Ubuntu Cleaning tagged **[SMME priority]**.
8. **Case-study duplicate:** as Finance, link INV002 and then INV008 to PO003 (`/link-po`). The second gets `AMOUNT_EXCEEDS_PO`, because both bill the same R35,000 order.

### Other business rules (with tests)

- **Supplier onboarding:**
  - CIPC, VAT and CSD formats are validated.
  - Exact duplicates are blocked.
  - Similar names need acknowledgement.
  - New suppliers start as `PENDING`.
- **Enforced by the database:**
  - Duplicate invoice numbers per supplier are blocked, whatever the formatting.
  - A PO's requester can't approve it.
  - A `PAID` invoice must have a payment date.
  - The audit log is append-only and hash-chained.
- **Security:**
  - Passwords are hashed with Argon2id.
  - Sign-in uses JWT tokens.
  - Login errors don't reveal which accounts exist.
  - The app refuses to start outside local/test with the default secret.
  - Errors use one consistent JSON format.

## Repository layout

```
backend/
  app/            FastAPI app: api/ routes, core/ config+security+errors, models/, schemas/,
                  services/ (business rules: workflow, sla, suppliers, audit), worker.py (Celery)
  migrations/     Alembic; schema lives in reviewed SQL files (migrations/sql)
  seed/           Case-study data, reproduced exactly, + demo users
  tests/          pytest suite (real PostgreSQL)
docs/             Architecture, ERD, design viewer
.github/workflows CI
```

## Roadmap

1. ~~Foundation: schema, auth and roles, seed, Docker, CI~~
2. ~~Invoice workflow: supplier submission, 3-way match, approval routing, SLA scheduler (Celery + Redis)~~
3. Risk engine: 8 explainable rules + Isolation Forest; investigation queue; precision/recall on labelled synthetic data
4. Spend intelligence: synthetic expansion, dbt star schema + tests, Dagster, Power BI report
5. React + TypeScript frontend: internal console and supplier portal
6. AWS deployment; Ask BlinkHub (LLM); certificate document AI

## Assumptions and limitations

See [`backend/seed/case_study.py`](backend/seed/case_study.py) (`ASSUMPTIONS`) and [docs/architecture.md §9](docs/architecture.md).
