# BlinkHub Procurement Intelligence & Risk Engine

A working prototype for the **BlinkHub Procurement Innovation Challenge** (MICS scenario). It gives Mzansi Infrastructure & Community Services one trustworthy view of the procure-to-pay chain: where the money goes, which invoices are stuck and why, and which transactions need investigating.

> **All data is fictional.** The seed reproduces the case study's sample records exactly. On top of that, a **synthetic demonstration year** is generated (~450 suppliers, ~R85m, deterministic seed) with deliberately planted anomalies. It is labelled as synthetic everywhere and must never be presented as MICS's actual performance.

![CI](https://github.com/DayDay0308/blinkhub-procurement-intelligence/actions/workflows/ci.yml/badge.svg)

## Problems addressed

| Case study problem | What this solves |
|---|---|
| 3. Where is the money? | Spend by department, supplier, category and province; SMME share; concentration |
| 4. The invoice that never gets paid | Invoice ageing, 30-day SLA ladder, accountable approver, supplier self-service status |
| 6. Something doesn't look right | Explainable risk flags in an investigation queue: 8 rules + an ML model, with measured precision/recall |
| Blink: "track supplier performance" | Supplier scorecards: delivery, invoice accuracy, compliance, risk record, price |
| 3. Where is the money? (Path B) | dbt star schema (40 data tests), Dagster schedule, **Power BI report**, analysis notebook answering the 7 investigation questions |

Full reasoning: [docs/architecture.md](docs/architecture.md) · Data model: [docs/erd.md](docs/erd.md)

## Quick start (Docker)

Requires Docker Desktop.

```bash
git clone https://github.com/DayDay0308/blinkhub-procurement-intelligence.git
cd blinkhub-procurement-intelligence
cp .env.example .env          # Windows PowerShell: copy .env.example .env
docker compose up --build
```

On first start, the API applies database migrations, loads the case-study data, generates the synthetic year and runs an initial risk scan (about 15 seconds). Set `SEED_SYNTHETIC=false` in `.env` to load only the 8 case-study suppliers.

| What | Where |
|---|---|
| Interactive API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| PostgreSQL (Power BI, DBeaver) | `localhost:5432`, db `blinkhub`, user/password from `.env` |
| Worker logs (SLA job) | `docker compose logs -f worker` |
| **Dagster** (dbt lineage, runs, schedule) | http://localhost:3000 |
| **Power BI** | double-click `powerbi/blinkhub.pbids`; full guide in [`powerbi/README.md`](powerbi/README.md) |
| **Analysis notebook (Path B)** | [`analysis/01_procurement_analysis.ipynb`](analysis/01_procurement_analysis.ipynb) (renders on GitHub) |

### Check everything works (run before every demo)

```bash
python scripts/demo_check.py        # Windows, if `python` isn't found: uv run --no-project python scripts/demo_check.py
```

This runs the whole story against the running stack the way real users would:
1. all roles sign in
2. the case-study data and its 5 overdue invoices are present
3. a supplier submits an invoice, it's delivered, approved and paid, and the supplier sees the timeline
4. SLA alerts fire
5. the risk scan flags the case-study duplicates, and detection rates hold
6. scorecards are computed
7. the dbt marts match the Power BI check numbers, and all 5 containers plus Dagster are up

It prints PASS or FAIL for each step, is safe to run repeatedly, and needs only the Python standard library.

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
| POST | `/risk/run` · GET `/risk/summary` · `/risk/evaluation` | Manager, Auditor, Admin |
| GET | `/risk/flags` (`status`, `severity`, `rule_code`, `supplier_id`, `assigned_to_me`) · `/risk/flags/{id}` | Staff (never suppliers) |
| POST | `/risk/flags/{id}/status` · `/assign` | Auditor, Manager (closing needs a note; only managers reopen) |
| POST | `/risk/flags/{id}/notes` | Staff |
| GET/PATCH | `/risk/rules` · `/risk/rules/{code}` | Staff view · Admin tunes |
| GET | `/scorecards` · `/suppliers/{id}/scorecard` | Staff · supplier sees own |

### Demo script (Swagger)

1. Sign in as **`accounts@thutosupplies.demo`** and `POST /invoices` with `{"invoice_number": "TS-1001", "po_number": "PO010", "amount": 42000, "invoice_date": "<today>"}`. The result is `EXCEPTION` with the reason `AWAITING_GOODS_RECEIPT`.
2. Submit the same invoice as `ts 1001`. It's blocked with `409`.
3. Sign in as **`procurement@mics.demo`** and `POST /purchase-orders/PO010/goods-receipts` with `{"amount_received": 42000, "received_date": "<today>"}`. The invoice moves to `PENDING_APPROVAL`, owned by Anele (Approver).
4. Sign in as **`approver@mics.demo`**. `GET /invoices?assigned_to_me=true` lists it; `POST /invoices/{id}/approve`.
5. Sign in as **`finance@mics.demo`** and `POST /invoices/{id}/pay`.
6. Back as Thuto, `GET /invoices/{id}/timeline` shows submitted → exception → routed → approved → paid.
7. As **`manager@mics.demo`**, `POST /jobs/sla-check`, then `GET /notifications`. The breached invoices appear, with Ubuntu Cleaning tagged **[SMME priority]**.
8. **Case-study duplicate:** as Finance, link INV002 and then INV008 to PO003 (`/link-po`). The second gets `AMOUNT_EXCEEDS_PO`, because both bill the same R35,000 order.

### Supplier Performance & Risk (Problem 6 + Blink KPI tracking)

**Risk engine:** set-based SQL rules plus an Isolation Forest model. It runs nightly at 02:00 in the worker, or on demand with `POST /risk/run`. Every flag carries its evidence and a plain-English reason, and lands in an investigation queue. Only a person can **confirm** or **dismiss** a flag, and that needs a written note; both actions are recorded in the audit log.

| Rule | Problem 6 example | Logic |
|---|---|---|
| `DUP_INVOICE` | Same invoice twice | Same supplier and amount: on the same PO; or one without a PO within 60 days; or different POs raised within 7 days. Recurring monthly contracts are excluded. Flags the invoice that can't be matched, or the one still to be paid |
| `SPLIT_THRESHOLD` | Payments just below a threshold | 3+ orders from one supplier to one department within 30 days, each at 90–100% of an approval limit |
| `NO_DELIVERY_EVIDENCE` | Paid without delivery documentation | Approved or paid invoice with no PO or no goods receipt |
| `BANK_CHANGE_BEFORE_PAY` | Bank details changed before payment | Paid into an account that replaced the previous one within 14 days |
| `QUOTE_SIMILARITY` | Unusually similar pricing | 3+ quotes with a coefficient of variation below 2% |
| `CONCENTRATION` | Disproportionate share | Top supplier holds more than 40% of a category's 12-month spend (with HHI) |
| `INCOMPLETE_COMPLIANCE` | Incomplete supplier information | Active supplier paid recently without a valid tax clearance |
| `ANOMALY_ML` | Unusual expenditure | Isolation Forest; each flag lists the features driving it, e.g. "18.4x this supplier's typical invoice" |

Thresholds are stored in `risk.rules.params`, and an Admin can tune them with `PATCH /risk/rules/{code}` without a deploy.

**Measured, not claimed.** The synthetic generator plants labelled anomalies of each type (`synthetic.anomaly_labels`), and `GET /risk/evaluation` scores the engine against them:

| | Planted | Caught | Recall | Precision |
|---|---|---|---|---|
| 7 SQL rules | 109 | 109 | **100%** | **95–100%** per rule |
| ML (Isolation Forest) | 15 | 14 | 93% | 58%: a second opinion, which is why it's paired with rules |
| **Overall** | **124** | **123** | **99.2%** | **89.8%** (93.4% counting real problems caught by another rule) |

CI fails if any SQL rule drops below 95% recall or precision (`tests/test_synthetic_detection.py`).

**Supplier scorecards** (`GET /scorecards`, `GET /suppliers/{id}/scorecard`) give each supplier a score from 0 to 100 and a grade from A to E, weighted as follows:
- delivery reliability: 30%
- invoice accuracy: 25%
- compliance: 20%
- risk record: 15%
- price compared with the market median for the same item: 10%

KPIs with no data are re-weighted. Suppliers with no activity show `N/A`, so they're never ranked above suppliers with a real track record. Suppliers can see their own scorecard.

#### Risk demo (Swagger)

1. Sign in as **`auditor@mics.demo`** and call `GET /risk/flags`. The queue is sorted by score, with bank-change and split-order cases at the top.
2. Call `GET /risk/flags?rule_code=DUP_INVOICE`. This includes the **case-study duplicates**: INV008 (matches INV002) and INV006 (matches INV001, already paid).
3. Open a flag, then `POST /risk/flags/{id}/status` with `{"status": "CONFIRMED", "note": "..."}`. Without a note, the request is rejected.
4. Call `GET /risk/evaluation` for the precision and recall table, then `GET /scorecards?supplier_type=SMME` for the SMME ranking.

### Procurement Intelligence (Problem 3, Path B)

**Analysis notebook:** [`analysis/01_procurement_analysis.ipynb`](analysis/01_procurement_analysis.ipynb). It starts from the case-study tables *exactly as printed* ("R85,000", "KZN"), then:
- cleans and validates them with 6 data-quality checks
- answers all **7 investigation questions** with charts
- extends the analysis with the synthetic year, clearly labelled
- ends with findings, 8 costed recommendations, and assumptions and limitations

**dbt** (`analytics/dbt`) builds a star schema in the `analytics` schema:
- **Dimensions:** `dim_supplier` (with B-BBEE procurement recognition, Level 1 = 135%), `dim_date` (SA fiscal year Apr–Mar), `dim_department`, `dim_category`.
- **Facts:**
  - `fct_purchase_orders` (spend)
  - `fct_invoices` (days to pay, ageing, paid within terms)
  - `fct_deliveries` (on-time)
  - `fct_risk_flags` (value at risk)
- **Marts:** monthly KPIs, Pareto/ABC supplier ranking, HHI concentration.
- **Tests:** 40 data tests, including *every rand of PO spend reconciles to the app*, *no invoice paid before it was received* and referential integrity. A dbt **exposure** documents the Power BI dependency.
- **Every row carries `data_source`** (`CASE_STUDY` or `SYNTHETIC`), so no report can mix up real and demo data without saying so.

**Dagster** (`analytics/orchestration`) turns each dbt model into an asset with full lineage. It's scheduled daily at **03:00**, after the worker's 02:00 risk scan. The UI is at http://localhost:3000.

**Power BI** (`powerbi/`) has a four-page report spec:
1. Executive overview
2. Spend & SMME
3. Invoice performance
4. Risk & supplier performance

The kit includes a one-click connection file (`.pbids`), a theme, 30+ DAX measures (SMME share, B-BBEE recognition, HHI, days-to-pay gap, value under review…) and the expected numbers to check against.

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
                  services/ (business rules: workflow, sla, suppliers, audit, scorecard,
                  risk/ rules + ML + evaluation), worker.py (Celery)
  migrations/     Alembic; schema lives in reviewed SQL files (migrations/sql)
  seed/           case_study.py (exact sample data) · synthetic.py (demo year + planted anomalies)
  tests/          pytest suite (real PostgreSQL)
analytics/        dbt project (staging -> marts) + Dagster orchestration
analysis/         Path B notebook, raw case-study CSVs, synthetic snapshot
powerbi/          Power BI connection file, theme, DAX measures, build guide
docs/             Architecture, ERD, design viewer
.github/workflows CI
```

## Roadmap

1. ~~Foundation: schema, auth and roles, seed, Docker, CI~~
2. ~~Invoice workflow: supplier submission, 3-way match, approval routing, SLA scheduler (Celery + Redis)~~
3. ~~Risk engine: 8 explainable rules + Isolation Forest; investigation queue; precision/recall on labelled synthetic data; supplier scorecards~~
4. ~~Spend intelligence: dbt star schema + tests, Dagster, Power BI report, analysis notebook (Path B)~~
5. React + TypeScript frontend: internal console and supplier portal
6. AWS deployment; Ask BlinkHub (LLM); certificate document AI

## Assumptions and limitations

See [`backend/seed/case_study.py`](backend/seed/case_study.py) (`ASSUMPTIONS`) and [docs/architecture.md §9](docs/architecture.md).
