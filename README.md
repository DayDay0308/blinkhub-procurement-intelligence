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

**API endpoints** (`/api/v1`)

| Method | Path | Access |
|---|---|---|
| POST | `/auth/login` | Public |
| GET | `/auth/me` | Signed in |
| GET | `/suppliers` (search, filter by province/type/status) | Internal staff |
| GET | `/suppliers/{id}` | Internal staff; supplier for own profile |
| POST | `/suppliers` | Procurement Officer, Admin |
| GET | `/invoices` (filter `status`, `overdue`; sort) | Signed in; suppliers scoped to their own |
| GET | `/invoices/{id}` | Same scoping; other suppliers' invoices return 404 |

**Business rules, with tests**

- **Invoice ageing and SLA ladder:** warning at day 20, escalation at day 25, breach after day 30.
- **Exceptions shown on every invoice:** `MISSING_PO_REFERENCE`, `AMOUNT_EXCEEDS_PO`, `NO_ACCOUNTABLE_APPROVER`.
- **Supplier onboarding:**
  - CIPC, VAT and CSD number formats are validated.
  - Exact duplicates (same registration, VAT or CSD number) are blocked.
  - Similar names (trigram similarity ≥ 0.6) need an explicit acknowledgement.
  - New suppliers start as `PENDING`.
- **Enforced by the database:**
  - Duplicate invoice numbers per supplier are blocked, even with different formatting (`INV-001` = `inv 001`).
  - A PO's requester cannot approve it.
  - A `PAID` invoice must have a payment date.
  - The audit log is append-only and hash-chained.
- **Security:**
  - Passwords are hashed with Argon2id.
  - Sign-in uses JWT tokens.
  - Unknown-email and wrong-password logins return identical errors.
  - The app refuses to start outside local/test with the default secret.
  - Errors use one consistent JSON format.

## Repository layout

```
backend/
  app/            FastAPI app: api/ routes, core/ config+security+errors, models/, schemas/, services/ (business rules)
  migrations/     Alembic; schema lives in reviewed SQL files (migrations/sql)
  seed/           Case-study data, reproduced exactly, + demo users
  tests/          pytest suite (real PostgreSQL)
docs/             Architecture, ERD, design viewer
.github/workflows CI
```

## Roadmap

1. ~~Foundation: schema, auth and roles, seed, Docker, CI~~
2. Invoice workflow: supplier submission, 3-way match, approval routing, SLA scheduler (Celery + Redis)
3. Risk engine: 8 explainable rules + Isolation Forest; investigation queue; precision/recall on labelled synthetic data
4. Spend intelligence: synthetic expansion, dbt star schema + tests, Dagster, Power BI report
5. React + TypeScript frontend: internal console and supplier portal
6. AWS deployment; Ask BlinkHub (LLM); certificate document AI

## Assumptions and limitations

See [`backend/seed/case_study.py`](backend/seed/case_study.py) (`ASSUMPTIONS`) and [docs/architecture.md §9](docs/architecture.md).
