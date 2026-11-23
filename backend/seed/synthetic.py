"""Synthetic procurement year for MICS: DEMONSTRATION DATA ONLY.

Scales the case study up to the brief's figures (~450 suppliers, ~R85m a year) so trends,
dashboards and the risk engine have enough data to be meaningful. Everything is generated
from a fixed random seed, so every run produces the same data.

Two kinds of data:
1. "Normal" business: suppliers, POs, deliveries, invoices and payments with realistic
   patterns, including legitimate look-alikes the risk rules must NOT flag, such as monthly
   service contracts billing the same amount every month.
2. Planted anomalies, one set for each Problem 6 example. Each is recorded in
   synthetic.anomaly_labels, the answer key used to measure precision and recall.

Simulated patterns, such as SMMEs being paid more slowly than large suppliers, mirror the
case-study sample on purpose. They must never be presented as MICS's actual performance.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    Category,
    Department,
    Document,
    GoodsReceipt,
    Invoice,
    Opportunity,
    Payment,
    PurchaseOrder,
    PurchaseOrderLine,
    Quotation,
    Supplier,
    SupplierCategory,
    User,
)

# ------------------------------------------------------------------------- reference data
NEW_DEPARTMENTS = [("COM", "Community Services"), ("ICT", "ICT")]

# category name -> (code, item catalogue [(item_code, description, unit, base unit price)])
CATALOGUE: dict[str, tuple[str, list[tuple[str, str, str, float]]]] = {
    "Cleaning": (
        "CLN",
        [
            ("CLN-SVC", "Office cleaning service (month)", "MONTH", 18000),
            ("CLN-CHEM", "Cleaning chemicals 25L", "EA", 950),
            ("CLN-HYG", "Hygiene service per unit", "EA", 120),
        ],
    ),
    "Stationery": (
        "STA",
        [
            ("STA-A4", "A4 paper box (5 reams)", "BOX", 420),
            ("STA-TON", "Printer toner cartridge", "EA", 1450),
            ("STA-PEN", "Pens (box of 50)", "BOX", 160),
        ],
    ),
    "Transport": (
        "TRN",
        [
            ("TRN-BUS", "Staff bus hire (day)", "DAY", 6500),
            ("TRN-TRK", "Truck hire with driver (day)", "DAY", 9800),
            ("TRN-KM", "Fleet kilometres", "KM", 14),
        ],
    ),
    "Maintenance": (
        "MNT",
        [
            ("MNT-HR", "Artisan labour hour", "HR", 480),
            ("MNT-HVAC", "HVAC service visit", "EA", 7200),
            ("MNT-PLB", "Plumbing call-out", "EA", 2100),
        ],
    ),
    "Construction": (
        "CON",
        [
            ("CON-M2", "Paving per square metre", "M2", 620),
            ("CON-CONC", "Concrete per cubic metre", "M3", 1850),
            ("CON-PM", "Site project management (week)", "WEEK", 38000),
        ],
    ),
    "Security": (
        "SEC",
        [
            ("SEC-GRD", "Security guard shift", "SHIFT", 1150),
            ("SEC-CCTV", "CCTV camera installed", "EA", 6800),
        ],
    ),
    "ICT Equipment": (
        "ICTE",
        [
            ("ICT-LAP", "Laptop", "EA", 17500),
            ("ICT-MON", "Monitor 24 inch", "EA", 3100),
            ("ICT-SW", "Network switch", "EA", 9400),
        ],
    ),
    "Catering": (
        "CAT",
        [("CAT-MEAL", "Meal per person", "EA", 145), ("CAT-EVT", "Event catering package", "EA", 21000)],
    ),
    "Professional Services": (
        "PRO",
        [("PRO-HR", "Consulting hour", "HR", 1650), ("PRO-AUD", "Audit engagement", "EA", 145000)],
    ),
    "Electrical": (
        "ELE",
        [
            ("ELE-HR", "Electrician hour", "HR", 520),
            ("ELE-LGT", "LED light fitting", "EA", 690),
            ("ELE-DB", "Distribution board install", "EA", 14500),
        ],
    ),
    "Waste Management": (
        "WST",
        [("WST-SKIP", "Skip collection", "EA", 2400), ("WST-TON", "Waste disposal per ton", "TON", 980)],
    ),
}
SERVICE_CATEGORIES = ("Cleaning", "Security")  # recurring monthly contracts
CONCENTRATED_CATEGORIES = ("Waste Management", "Catering")  # planted concentration

PROVINCES = [
    "GAUTENG",
    "KWAZULU_NATAL",
    "WESTERN_CAPE",
    "LIMPOPO",
    "MPUMALANGA",
    "EASTERN_CAPE",
    "NORTH_WEST",
    "FREE_STATE",
    "NORTHERN_CAPE",
]
PROVINCE_WEIGHTS = [0.42, 0.14, 0.10, 0.08, 0.07, 0.07, 0.05, 0.04, 0.03]

NAME_STEMS = [
    "Ithemba",
    "Masakhane",
    "Kgotso",
    "Lesedi",
    "Bokamoso",
    "Siyakhula",
    "Imbali",
    "Phakama",
    "Amandla",
    "Kopano",
    "Simunye",
    "Letsatsi",
    "Thuthuka",
    "Vukani",
    "Zenzele",
    "Indlovu",
    "Mvelo",
    "Khanyisa",
    "Boitumelo",
    "Naledi",
    "Tswelelo",
    "Sizwe",
    "Lethabo",
    "Nkanyezi",
    "Mpumelelo",
    "Ntsika",
    "Hlanganani",
    "Re a Fala",
    "Kagiso",
    "Sedibeng",
    "Morena",
    "Botshabelo",
    "Isibane",
    "Umoya",
    "Lwazi",
    "Bophelo",
    "Tshepo",
    "Molemo",
    "Nandi",
    "Sakhile",
    "Sunrise",
    "Blue Crane",
    "Highveld",
    "Karoo",
    "Summit",
    "Keystone",
    "Meridian",
    "Granite",
    "Baobab",
    "Acacia",
    "Protea",
    "Marula",
    "Fynbos",
    "Ridgeway",
    "Northgate",
    "Riverside",
]
NAME_TAILS = {
    "Cleaning": ["Cleaning", "Hygiene", "Facility Care"],
    "Stationery": ["Office Supplies", "Stationers", "Paper & Print"],
    "Transport": ["Logistics", "Transport", "Fleet Services"],
    "Maintenance": ["Maintenance", "Property Care", "Technical Services"],
    "Construction": ["Civils", "Construction", "Builders"],
    "Security": ["Security", "Protection Services", "Guarding"],
    "ICT Equipment": ["Technologies", "IT Solutions", "Digital"],
    "Catering": ["Catering", "Hospitality", "Kitchens"],
    "Professional Services": ["Consulting", "Advisory", "Associates"],
    "Electrical": ["Electrical", "Power Solutions", "Electrotech"],
    "Waste Management": ["Waste Solutions", "Recycling", "Environmental"],
}
SUFFIXES = ["", " (Pty) Ltd", " Holdings", " Enterprises", " Projects", " Group"]


@dataclass
class Config:
    n_suppliers: int = 442  # + the 8 case-study suppliers = 450
    n_pos: int = 2600
    target_spend: float = 70_500_000  # + planted extras + R4.03m case-study sample ~= R85m
    months: int = 12
    n_opportunities: int = 120
    seed: int = 42
    # planted anomaly counts
    duplicates: int = 25
    split_schemes: int = 8
    no_delivery: int = 20
    bank_changes: int = 10
    collusion: int = 8
    non_compliant: int = 15
    unusual_amounts: int = 15
    # compliance documents (not risk anomalies; see _compliance_variety)
    docs_expiring: int = 18
    docs_missing: int = 12
    docs_pending: int = 6


@dataclass
class _State:
    now: datetime
    rng: np.random.Generator
    depts: dict[str, uuid.UUID] = field(default_factory=dict)
    cats: dict[str, uuid.UUID] = field(default_factory=dict)
    suppliers: list[dict] = field(default_factory=list)
    users: dict[str, list[dict]] = field(default_factory=dict)
    pos: list[dict] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)
    grns: list[dict] = field(default_factory=list)
    invoices: list[dict] = field(default_factory=list)
    payments: list[dict] = field(default_factory=list)
    banks: list[dict] = field(default_factory=list)
    docs: list[dict] = field(default_factory=list)
    opps: list[dict] = field(default_factory=list)
    quotes: list[dict] = field(default_factory=list)
    labels: list[dict] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)

    def next(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def label(self, anomaly: str, entity_type: str, entity_id: uuid.UUID, **detail) -> None:
        self.labels.append(
            {
                "anomaly_type": anomaly,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "detail": json.dumps(detail, default=str),
            }
        )


def money(x: float) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def uid() -> uuid.UUID:
    return uuid.uuid4()


# ------------------------------------------------------------------------- master data
def _reference_data(db: Session, st: _State) -> None:
    for code, name in NEW_DEPARTMENTS:
        if not db.scalar(select(Department.id).where(Department.name == name)):
            db.add(Department(code=code, name=name))
    for name, (code, _) in CATALOGUE.items():
        if not db.scalar(select(Category.id).where(Category.name == name)):
            db.add(Category(code=code, name=name))
    db.flush()
    st.depts = {d.name: d.id for d in db.scalars(select(Department))}
    st.cats = {c.name: c.id for c in db.scalars(select(Category))}


def _users(db: Session, st: _State) -> None:
    pw = hash_password("Demo@2026!")
    existing = {u.email: u for u in db.scalars(select(User))}
    wanted = [
        (f"approver.{d.lower().replace(' ', '')}@mics.demo", f"{d} Approver", "APPROVER", d, 50_000)
        for d in st.depts
        if d != "Infrastructure"
    ]
    wanted += [
        ("procurement2@mics.demo", "Pieter Procurement", "PROCUREMENT_OFFICER", "Facilities", None),
        ("procurement3@mics.demo", "Precious Procurement", "PROCUREMENT_OFFICER", "ICT", None),
        ("finance2@mics.demo", "Fikile Finance", "FINANCE_OFFICER", None, 500_000),
    ]
    for email, name, role, dept, limit in wanted:
        if email not in existing:
            db.add(
                User(
                    email=email,
                    full_name=name,
                    role=role,
                    password_hash=pw,
                    department_id=st.depts.get(dept) if dept else None,
                    approval_limit=Decimal(limit) if limit else None,
                )
            )
    db.flush()
    by_role: dict[str, list[dict]] = {}
    for u in db.scalars(select(User).where(User.role != "SUPPLIER")):
        by_role.setdefault(u.role, []).append(
            {"id": u.id, "dept": u.department_id, "limit": float(u.approval_limit or 0)}
        )
    st.users = by_role


def _suppliers(st: _State, cfg: Config) -> None:
    rng = st.rng
    cat_names = list(CATALOGUE)
    used: set[str] = set()
    for i in range(cfg.n_suppliers):
        primary = cat_names[i % len(cat_names)] if i < len(cat_names) * 20 else rng.choice(cat_names)
        cats = [primary]
        if rng.random() < 0.25:
            cats.append(str(rng.choice([c for c in cat_names if c != primary])))
        for _ in range(50):
            name = f"{rng.choice(NAME_STEMS)} {rng.choice(NAME_TAILS[primary])}{rng.choice(SUFFIXES)}"
            if name not in used:
                break
        else:
            name = f"{name} {i}"
        used.add(name)
        large = rng.random() < 0.28
        typ = "LARGE_ENTERPRISE" if large else "SMME"
        r = rng.random()
        status = "ACTIVE" if r < 0.92 else ("INACTIVE" if r < 0.97 else "SUSPENDED")
        level = (
            int(rng.choice([1, 2, 3, 4, 5, 6, 8], p=[0.14, 0.22, 0.2, 0.2, 0.1, 0.08, 0.06]))
            if large
            else int(rng.choice([1, 2, 3, 4], p=[0.55, 0.3, 0.1, 0.05]))
        )
        black = float(rng.choice([100, 51, 30, 26, 0], p=[0.45, 0.25, 0.1, 0.1, 0.1]))
        women = float(min(black, rng.choice([0, 30, 51, 100], p=[0.35, 0.3, 0.2, 0.15])))
        st.suppliers.append(
            {
                "id": uid(),
                "supplier_code": f"SYN-{i + 1:05d}",
                "legal_name": name,
                "registration_number": f"{rng.integers(1998, 2025)}/{600000 + i:06d}/07",
                "vat_number": f"4{100_000_000 + i * 1931:09d}" if large or rng.random() < 0.5 else None,
                "csd_number": f"MAAA{1_200_000 + i:07d}",
                "province": str(rng.choice(PROVINCES, p=PROVINCE_WEIGHTS)),
                "supplier_type": typ,
                "enterprise_size": "GENERIC" if large else str(rng.choice(["EME", "QSE"], p=[0.6, 0.4])),
                "bbbee_level": level,
                "black_owned_pct": money(black),
                "black_women_owned_pct": money(women),
                "status": status,
                "email": f"accounts@{name.split()[0].lower()}{i}.demo",
                "created_at": st.now - timedelta(days=int(rng.integers(400, 3000))),
                # simulation-only attributes (not stored)
                "_cats": cats,
                "_large": large,
                "_weight": float(rng.lognormal(1.1, 0.45) if large else rng.lognormal(0.0, 0.5)),
                "_on_time": float(rng.beta(9, 2) if rng.random() < 0.85 else rng.beta(3, 3)),
                "_pay_days": float(rng.gamma(4, 4) if large else rng.gamma(6, 5.5)),
                "_price": float(rng.normal(1.0, 0.07) if rng.random() < 0.93 else rng.normal(1.3, 0.05)),
            }
        )


def _banks_and_docs(st: _State) -> None:
    rng, now = st.rng, st.now
    banks = ["FNB", "Standard Bank", "Absa", "Nedbank", "Capitec", "Investec", "TymeBank"]
    for s in st.suppliers:
        s["_bank_id"] = uid()
        st.banks.append(
            {
                "id": s["_bank_id"],
                "supplier_id": s["id"],
                "bank_name": str(rng.choice(banks)),
                "number": f"{rng.integers(10**9, 10**10)}",
                "verified": True,
                "effective_from": s["created_at"],
                "effective_to": None,
            }
        )
        for doc_type in ("TAX_CLEARANCE", "BBBEE_CERTIFICATE"):
            expired = s["status"] != "ACTIVE" and rng.random() < 0.4
            if expired:
                expiry = (now - timedelta(days=int(rng.integers(10, 200)))).date()
                issued = expiry - timedelta(days=365)
            else:
                issued = (now - timedelta(days=int(rng.integers(20, 300)))).date()
                expiry = issued + timedelta(days=365)
            st.docs.append(
                {
                    "supplier_id": s["id"],
                    "doc_type": doc_type,
                    "storage_key": f"synthetic/{s['supplier_code']}/{doc_type.lower()}.pdf",
                    "sha256": hashlib.sha256(f"{s['id']}{doc_type}".encode()).hexdigest(),
                    "issue_date": issued,
                    "expiry_date": expiry,
                    "status": "EXPIRED" if expired else "VERIFIED",
                    "uploaded_at": datetime.combine(issued, datetime.min.time(), UTC),
                }
            )


# ------------------------------------------------------------------------- transactions
def _approver_for(st: _State, dept_id: uuid.UUID, amount: float, exclude: uuid.UUID) -> uuid.UUID:
    pool = [
        u
        for u in st.users.get("APPROVER", []) + st.users.get("FINANCE_OFFICER", [])
        if u["limit"] >= amount and u["id"] != exclude
    ]
    pool.sort(key=lambda u: (u["dept"] != dept_id, u["limit"]))
    if pool:
        return pool[0]["id"]
    return st.users["MANAGER"][0]["id"]


def _make_po(
    st: _State,
    s: dict,
    cat: str,
    amount: float,
    created: datetime,
    *,
    dept: str | None = None,
    receive: bool = True,
    invoice: bool = True,
    fixed_items: tuple | None = None,
) -> dict:
    rng, now = st.rng, st.now
    dept = dept or str(rng.choice(list(st.depts)))
    creator = st.users["PROCUREMENT_OFFICER"][int(rng.integers(len(st.users["PROCUREMENT_OFFICER"])))]["id"]
    approver = _approver_for(st, st.depts[dept], amount, creator)
    lead = int(rng.integers(5, 30))
    n = st.next("po")
    po = {
        "id": uid(),
        "po_number": f"SPO{n:06d}",
        "supplier_id": s["id"],
        "department_id": st.depts[dept],
        "category_id": st.cats[cat],
        "delivery_province": s["province"],
        "total_amount": money(amount),
        "status": "APPROVED",
        "created_by": creator,
        "approved_by": approver,
        "approved_at": created + timedelta(hours=int(rng.integers(2, 72))),
        "created_at": created,
        "expected_delivery_date": (created + timedelta(days=lead)).date(),
    }
    st.pos.append(po)

    # lines: pick catalogue items, priced with the supplier's price factor, scaled to amount
    items = CATALOGUE[cat][1]
    chosen = (
        [fixed_items]
        if fixed_items
        else [
            items[int(i)]
            for i in rng.choice(len(items), size=min(len(items), int(rng.integers(1, 3))), replace=False)
        ]
    )
    remaining = amount
    for ln, (code, desc, unit, base) in enumerate(chosen, start=1):
        share = remaining if ln == len(chosen) else remaining * float(rng.uniform(0.3, 0.7))
        unit_price = max(1.0, base * s["_price"] * float(rng.normal(1, 0.03)))
        qty = max(1, round(share / unit_price))
        unit_price = share / qty
        st.lines.append(
            {
                "po_id": po["id"],
                "line_no": ln,
                "item_code": code,
                "description": desc,
                "quantity": Decimal(qty),
                "unit": unit,
                "unit_price": money(unit_price),
            }
        )
        remaining -= share

    expected = created + timedelta(days=lead)
    on_time = rng.random() < s["_on_time"]
    received_at = (
        expected - timedelta(days=int(rng.integers(0, 3)))
        if on_time
        else expected + timedelta(days=int(rng.integers(2, 21)))
    )
    po["_received_at"] = received_at
    if not receive or received_at > now:
        return po
    st.grns.append(
        {
            "id": uid(),
            "grn_number": f"GRN-S{st.next('grn'):06d}",
            "po_id": po["id"],
            "received_date": received_at.date(),
            "amount_received": money(amount),
            "received_by": creator,
            "created_at": received_at,
        }
    )
    po["status"] = "RECEIVED"
    if invoice:
        _make_invoice(st, s, po, received_at + timedelta(days=int(rng.integers(0, 6))))
    return po


def _make_invoice(
    st: _State,
    s: dict,
    po: dict | None,
    inv_date: datetime,
    *,
    amount: Decimal | None = None,
    number: str | None = None,
    pay_after: float | None = None,
    force_unpaid: bool = False,
) -> dict | None:
    rng, now = st.rng, st.now
    if inv_date > now:
        return None
    received = inv_date + timedelta(hours=int(rng.integers(1, 60)))
    amount = amount if amount is not None else po["total_amount"]
    prefix = "".join(w[0] for w in s["legal_name"].split()[:2]).upper()
    inv = {
        "id": uid(),
        "supplier_id": s["id"],
        "po_id": po["id"] if po else None,
        "invoice_number": number or f"{prefix}-{st.next('inv'):05d}",
        "amount": amount,
        "vat_amount": money(float(amount) * 15 / 115),
        "invoice_date": inv_date.date(),
        "received_at": received,
        "due_date": (received + timedelta(days=30)).date(),
        "channel": str(rng.choice(["PORTAL", "EMAIL", "MANUAL"], p=[0.35, 0.5, 0.15])),
        "match_exceptions": [],
        "paid_at": None,
        "current_approver_id": None,
        "status": "PENDING_APPROVAL",
    }
    days = pay_after if pay_after is not None else max(3.0, float(rng.normal(s["_pay_days"], 5)))
    paid_at = received + timedelta(days=days)
    if paid_at <= now and not force_unpaid:
        inv["status"], inv["paid_at"] = "PAID", paid_at
        st.payments.append(
            {
                "id": uid(),
                "invoice_id": inv["id"],
                "bank_account_id": s["_bank_id"],
                "amount": amount,
                "paid_at": paid_at,
                "reference": f"PAY-S{st.next('pay'):07d}",
                "_supplier": s["id"],
            }
        )
    else:
        dept = po["department_id"] if po else None
        inv["current_approver_id"] = _approver_for(st, dept, float(amount), po["created_by"] if po else None)
    st.invoices.append(inv)
    return inv


def _normal_business(st: _State, cfg: Config) -> None:
    rng, now = st.rng, st.now
    start = now - timedelta(days=30 * cfg.months)
    active = [s for s in st.suppliers if s["status"] == "ACTIVE"]
    by_cat = {c: [s for s in active if c in s["_cats"]] for c in CATALOGUE}

    # planted concentration: one supplier gets most of THIS category only
    boost: dict[tuple[uuid.UUID, str], float] = {}
    for cat in CONCENTRATED_CATEGORIES:
        boss = max(by_cat[cat], key=lambda s: s["_weight"])
        boost[(boss["id"], cat)] = 40.0

    # monthly service contracts (legitimate repeated identical amounts)
    contracts = []
    for cat in SERVICE_CATEGORIES:
        for s in rng.choice(by_cat[cat], size=min(12, len(by_cat[cat])), replace=False):
            contracts.append((s, cat, float(rng.choice([18_000, 24_500, 36_000, 52_000, 68_000]))))
    for s, cat, monthly in contracts:
        item = CATALOGUE[cat][1][0]
        for m in range(cfg.months):
            created = start + timedelta(days=30 * m + int(rng.integers(0, 3)))
            _make_po(st, s, cat, monthly, created, dept="Facilities", fixed_items=item)

    # ad-hoc purchasing: category by volume, supplier by weight, lognormal amounts
    cat_weights = np.array([1.3, 0.8, 1.6, 1.2, 0.9, 0.9, 0.9, 0.5, 0.6, 1.0, 0.6])
    cat_weights /= cat_weights.sum()
    cats = list(CATALOGUE)
    scale = {"Construction": 11.5, "Professional Services": 11.2, "Transport": 10.8, "ICT Equipment": 10.6}
    for _ in range(cfg.n_pos - len(st.pos)):
        cat = cats[int(rng.choice(len(cats), p=cat_weights))]
        pool = by_cat[cat]
        w = np.array([s["_weight"] * boost.get((s["id"], cat), 1.0) for s in pool])
        s = pool[int(rng.choice(len(pool), p=w / w.sum()))]
        mu = scale.get(cat, 10.0) + (0.5 if s["_large"] else 0)
        amount = float(min(rng.lognormal(mu, 0.75), 2_500_000))
        created = start + timedelta(seconds=float(rng.uniform(0, (now - start).total_seconds())))
        _make_po(st, s, cat, max(800.0, amount), created)


def _scale_to_target(st: _State, target: float) -> None:
    total = float(sum(float(p["total_amount"]) for p in st.pos))
    k = target / total
    po_k = {}
    for p in st.pos:
        p["total_amount"] = money(float(p["total_amount"]) * k)
        po_k[p["id"]] = p["total_amount"]
    for ln in st.lines:
        ln["unit_price"] = money(float(ln["unit_price"]) * k)
    for g in st.grns:
        g["amount_received"] = po_k[g["po_id"]]
    for inv in st.invoices:
        if inv["po_id"]:
            inv["amount"] = po_k[inv["po_id"]]
            inv["vat_amount"] = money(float(inv["amount"]) * 15 / 115)
    pay_amount = {i["id"]: i["amount"] for i in st.invoices}
    for p in st.payments:
        p["amount"] = pay_amount[p["invoice_id"]]


# ------------------------------------------------------------------------- planted anomalies
def _plant(st: _State, cfg: Config) -> None:
    rng, now = st.rng, st.now
    sup = {s["id"]: s for s in st.suppliers}
    paid = [i for i in st.invoices if i["status"] == "PAID" and i["po_id"]]
    rng.shuffle(paid)
    used: set[uuid.UUID] = set()

    def take(pred) -> dict:
        for inv in paid:
            if inv["id"] not in used and pred(inv):
                used.add(inv["id"])
                return inv
        raise RuntimeError("not enough invoices to plant anomalies")

    # 1. Duplicate invoices: re-submitted copies of paid invoices
    for k in range(cfg.duplicates):
        orig = take(lambda i: (now - i["received_at"]).days > 40)
        s = sup[orig["supplier_id"]]
        same_po = k % 2 == 0
        dup_date = datetime.combine(orig["invoice_date"], datetime.min.time(), UTC) + timedelta(
            days=int(rng.integers(2, 25))
        )
        dup = _make_invoice(
            st,
            s,
            next(p for p in st.pos if p["id"] == orig["po_id"]) if same_po else None,
            dup_date,
            amount=orig["amount"],
            number=f"{orig['invoice_number']}-{'AB'[k % 2]}",
            force_unpaid=k % 3 != 0,
        )
        used.add(dup["id"])
        st.label("DUP_INVOICE", "INVOICE", dup["id"], original=orig["invoice_number"], same_po=same_po)

    # 2. Split purchases just under the R50,000 approval limit
    smmes = [s for s in st.suppliers if s["status"] == "ACTIVE" and not s["_large"]]
    for k in range(cfg.split_schemes):
        s = smmes[int(rng.integers(len(smmes)))]
        dept = str(rng.choice(["Facilities", "Operations", "Administration", "Community Services"]))
        base = now - timedelta(days=int(rng.integers(60, 300)))
        for j in range(int(rng.integers(3, 6))):
            po = _make_po(
                st,
                s,
                s["_cats"][0],
                float(rng.uniform(45_200, 49_950)),
                base + timedelta(days=j * int(rng.integers(3, 7))),
                dept=dept,
            )
            inv = next((i for i in st.invoices if i["po_id"] == po["id"]), None)
            if inv:
                used.add(inv["id"])
                st.label("SPLIT_THRESHOLD", "INVOICE", inv["id"], scheme=k, department=dept)

    # 3. Paid without delivery evidence: remove the goods receipt
    for _ in range(cfg.no_delivery):
        inv = take(lambda i: True)
        st.grns = [g for g in st.grns if g["po_id"] != inv["po_id"]]
        for p in st.pos:
            if p["id"] == inv["po_id"]:
                p["status"] = "APPROVED"
        st.label("NO_DELIVERY_EVIDENCE", "INVOICE", inv["id"])

    # 4. Bank details changed days before a payment (the supplier's latest payment)
    latest: dict[uuid.UUID, dict] = {}
    for p in st.payments:
        if p["_supplier"] not in latest or p["paid_at"] > latest[p["_supplier"]]["paid_at"]:
            latest[p["_supplier"]] = p
    candidates = [p for p in latest.values() if p["invoice_id"] not in used]
    rng.shuffle(candidates)
    for p in candidates[: cfg.bank_changes]:
        used.add(p["invoice_id"])
        changed = p["paid_at"] - timedelta(days=float(rng.uniform(1, 10)))
        old = next(b for b in st.banks if b["supplier_id"] == p["_supplier"] and b["effective_to"] is None)
        old["effective_to"] = changed
        new_id = uid()
        st.banks.append(
            {
                "id": new_id,
                "supplier_id": p["_supplier"],
                "bank_name": "Capitec",
                "number": f"{rng.integers(10**9, 10**10)}",
                "verified": True,
                "effective_from": changed,
                "effective_to": None,
            }
        )
        p["bank_account_id"] = new_id
        st.label("BANK_CHANGE_BEFORE_PAY", "INVOICE", p["invoice_id"])
    # legitimate bank changes long before any payment (must NOT be flagged)
    for s in [s for s in st.suppliers if s["id"] not in latest][:15]:
        old = next(b for b in st.banks if b["supplier_id"] == s["id"] and b["effective_to"] is None)
        old["effective_to"] = s["created_at"] + timedelta(days=30)
        st.banks.append({**old, "id": uid(), "effective_from": old["effective_to"], "effective_to": None})

    # 5. Paid while non-compliant: tax clearance expired, still being paid
    recent = {p["_supplier"] for p in st.payments if (now - p["paid_at"]).days < 60}
    pool = [s for s in st.suppliers if s["id"] in recent and s["status"] == "ACTIVE"]
    for s in [pool[int(i)] for i in rng.choice(len(pool), size=cfg.non_compliant, replace=False)]:
        for d in st.docs:
            if d["supplier_id"] == s["id"] and d["doc_type"] == "TAX_CLEARANCE":
                d["expiry_date"] = (now - timedelta(days=int(rng.integers(20, 150)))).date()
                d["issue_date"] = d["expiry_date"] - timedelta(days=365)
                d["status"] = "EXPIRED"
        st.label("INCOMPLETE_COMPLIANCE", "SUPPLIER", s["id"])

    # 6. Unusual amounts: far above the supplier's normal invoices
    counts: dict[uuid.UUID, int] = {}
    for i in st.invoices:
        counts[i["supplier_id"]] = counts.get(i["supplier_id"], 0) + 1
    # Only in big categories, so one inflated invoice doesn't also create a concentration signal.
    big = {
        st.cats[c]
        for c in (
            "Construction",
            "Transport",
            "Cleaning",
            "ICT Equipment",
            "Professional Services",
            "Maintenance",
        )
    }
    po_cat = {p["id"]: p["category_id"] for p in st.pos}
    for _ in range(cfg.unusual_amounts):
        inv = take(
            lambda i: (
                counts.get(i["supplier_id"], 0) >= 5
                and float(i["amount"]) < 60_000
                and po_cat.get(i["po_id"]) in big
            )
        )
        k = float(rng.uniform(15, 30))
        new_amount = money(float(inv["amount"]) * k)
        for p in st.pos:
            if p["id"] == inv["po_id"]:
                p["total_amount"] = new_amount
        for ln in st.lines:
            if ln["po_id"] == inv["po_id"]:
                ln["unit_price"] = money(float(ln["unit_price"]) * k)
        for g in st.grns:
            if g["po_id"] == inv["po_id"]:
                g["amount_received"] = new_amount
        inv["amount"], inv["vat_amount"] = new_amount, money(float(new_amount) * 15 / 115)
        for p in st.payments:
            if p["invoice_id"] == inv["id"]:
                p["amount"] = new_amount
        st.label("ANOMALY_ML", "INVOICE", inv["id"], multiplier=round(k, 1))

    for c in CONCENTRATED_CATEGORIES:
        st.label("CONCENTRATION", "CATEGORY", st.cats[c], category=c)


def _compliance_variety(st: _State, cfg: Config) -> None:
    """Make document expiry realistic for the compliance check: some certificates about to
    expire, some never received, some renewals waiting for verification.

    Uses its own random generator, so the planted risk anomalies above are unchanged, and
    avoids the suppliers planted as INCOMPLETE_COMPLIANCE (their tax clearance stays expired).
    """
    rng = np.random.default_rng(cfg.seed + 7)
    today = st.now.date()
    planted = {lab["entity_id"] for lab in st.labels if lab["anomaly_type"] == "INCOMPLETE_COMPLIANCE"}
    pool = [s["id"] for s in st.suppliers if s["status"] == "ACTIVE" and s["id"] not in planted]
    chosen = [
        pool[int(i)]
        for i in rng.choice(
            len(pool), size=cfg.docs_expiring + cfg.docs_missing + cfg.docs_pending, replace=False
        )
    ]
    expiring = chosen[: cfg.docs_expiring]
    missing = set(chosen[cfg.docs_expiring : cfg.docs_expiring + cfg.docs_missing])
    pending = chosen[cfg.docs_expiring + cfg.docs_missing :]

    for sid in expiring:
        d = next(d for d in st.docs if d["supplier_id"] == sid and d["doc_type"] == "TAX_CLEARANCE")
        d["expiry_date"] = today + timedelta(days=int(rng.integers(3, 30)))
        d["issue_date"] = d["expiry_date"] - timedelta(days=365)
        d["status"] = "VERIFIED"
    st.docs = [
        d for d in st.docs if not (d["supplier_id"] in missing and d["doc_type"] == "BBBEE_CERTIFICATE")
    ]
    by_code = {s["id"]: s["supplier_code"] for s in st.suppliers}
    for sid in pending:
        st.docs.append(
            {
                "supplier_id": sid,
                "doc_type": "TAX_CLEARANCE",
                "storage_key": f"synthetic/{by_code[sid]}/tax_clearance_renewal.pdf",
                "sha256": hashlib.sha256(f"{sid}TAX_CLEARANCE-renewal".encode()).hexdigest(),
                "issue_date": None,
                "expiry_date": today + timedelta(days=int(rng.integers(330, 400))),
                "status": "UPLOADED",
                "uploaded_at": st.now - timedelta(days=int(rng.integers(1, 6))),
            }
        )


def _opportunities(st: _State, cfg: Config) -> None:
    rng, now = st.rng, st.now
    active = [s for s in st.suppliers if s["status"] == "ACTIVE"]
    creator = st.users["PROCUREMENT_OFFICER"][0]["id"]
    collusive = set(rng.choice(cfg.n_opportunities, size=cfg.collusion, replace=False).tolist())
    for k in range(cfg.n_opportunities):
        cat = str(rng.choice(list(CATALOGUE)))
        pool = [s for s in active if cat in s["_cats"]]
        bidders = [
            pool[int(i)]
            for i in rng.choice(len(pool), size=min(len(pool), int(rng.integers(3, 6))), replace=False)
        ]
        value = float(rng.lognormal(12.2, 0.6))
        spread = 0.005 if k in collusive else float(rng.uniform(0.08, 0.25))
        amounts = [money(value * float(rng.uniform(1 - spread, 1 + spread))) for _ in bidders]
        closes = now - timedelta(days=int(rng.integers(10, 330)))
        winner = bidders[int(np.argmin([float(a) for a in amounts]))]
        opp = {
            "id": uid(),
            "reference": f"OPP-{2026}-{k + 1:04d}",
            "title": f"{cat} requirement {k + 1}",
            "category_id": st.cats[cat],
            "department_id": st.depts[str(rng.choice(list(st.depts)))],
            "province": str(rng.choice(PROVINCES, p=PROVINCE_WEIGHTS)),
            "estimated_value": money(value),
            "smme_set_aside": bool(rng.random() < 0.3),
            "closes_at": closes,
            "status": "AWARDED",
            "awarded_supplier_id": winner["id"],
            "created_by": creator,
            "created_at": closes - timedelta(days=21),
        }
        st.opps.append(opp)
        for s, a in zip(bidders, amounts, strict=True):
            st.quotes.append(
                {
                    "opportunity_id": opp["id"],
                    "supplier_id": s["id"],
                    "amount": a,
                    "submitted_at": closes - timedelta(days=int(rng.integers(1, 10))),
                }
            )
        if k in collusive:
            st.label("QUOTE_SIMILARITY", "OPPORTUNITY", opp["id"], spread_pct=0.5)


# ------------------------------------------------------------------------- write
def _strip(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


def _write(db: Session, st: _State) -> None:
    db.execute(insert(Supplier), _strip(st.suppliers))
    db.execute(
        insert(SupplierCategory),
        [{"supplier_id": s["id"], "category_id": st.cats[c]} for s in st.suppliers for c in s["_cats"]],
    )
    key = get_settings().data_encryption_key
    db.execute(
        text(
            "INSERT INTO compliance.bank_accounts (id, supplier_id, bank_name, account_number_enc, account_last4, "
            "branch_code, verified, effective_from, effective_to) VALUES (:id, :supplier_id, :bank_name, "
            "pgp_sym_encrypt(:number, :key), right(:number, 4), '250655', :verified, :effective_from, :effective_to)"
        ),
        [{**b, "key": key} for b in sorted(st.banks, key=lambda b: b["effective_from"])],
    )
    db.execute(insert(Document), st.docs)
    db.execute(insert(PurchaseOrder), _strip(st.pos))
    db.execute(insert(PurchaseOrderLine), st.lines)
    db.execute(insert(GoodsReceipt), st.grns)
    db.execute(insert(Invoice), st.invoices)
    db.execute(insert(Payment), _strip(st.payments))
    db.execute(insert(Opportunity), st.opps)
    db.execute(insert(Quotation), st.quotes)
    db.execute(
        text(
            "INSERT INTO synthetic.anomaly_labels (anomaly_type, entity_type, entity_id, detail) "
            "VALUES (:anomaly_type, :entity_type, :entity_id, CAST(:detail AS jsonb))"
        ),
        st.labels,
    )


def generate(db: Session, cfg: Config | None = None, now: datetime | None = None) -> dict[str, int]:
    cfg = cfg or Config()
    st = _State(now=now or datetime.now(UTC), rng=np.random.default_rng(cfg.seed))
    _reference_data(db, st)
    _users(db, st)
    _suppliers(st, cfg)
    _banks_and_docs(st)
    _normal_business(st, cfg)
    _scale_to_target(st, cfg.target_spend)
    _plant(st, cfg)
    _compliance_variety(st, cfg)
    _opportunities(st, cfg)
    _write(db, st)
    db.flush()
    return {
        "suppliers": len(st.suppliers),
        "purchase_orders": len(st.pos),
        "invoices": len(st.invoices),
        "payments": len(st.payments),
        "goods_receipts": len(st.grns),
        "opportunities": len(st.opps),
        "planted_anomalies": len(st.labels),
        "spend_rand": int(sum(float(p["total_amount"]) for p in st.pos)),
    }
