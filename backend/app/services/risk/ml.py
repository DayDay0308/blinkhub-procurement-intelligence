"""Isolation Forest anomaly detection over invoices.

Rules catch the patterns we anticipated; this model catches invoices that look unlike the
rest. An ML score alone is not evidence, so every flag names the features that made the
invoice unusual, using robust z-scores (median/MAD) that an investigator can check.
"""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import median

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import text
from sqlalchemy.orm import Session

FEATURES = {
    "amount_vs_supplier": "times this supplier's typical invoice",
    "amount_vs_category": "times the typical invoice in this category",
    "log_amount": "invoice size",
    "supplier_invoice_count": "number of invoices from this supplier",
    "round_amount": "suspiciously round amount",
    "weekend": "submitted on a weekend",
}


def _load(db: Session) -> list[dict]:
    rows = (
        db.execute(
            text("""
        SELECT i.id, i.supplier_id, i.amount::float AS amount, i.received_at, c.name AS category
        FROM p2p.invoices i
        LEFT JOIN p2p.purchase_orders po ON po.id = i.po_id
        LEFT JOIN core.categories c ON c.id = po.category_id
        WHERE i.status <> 'REJECTED'
    """)
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


def _features(rows: list[dict]) -> tuple[np.ndarray, list[str]]:
    by_supplier: dict = defaultdict(list)
    by_category: dict = defaultdict(list)
    for r in rows:
        by_supplier[r["supplier_id"]].append(r["amount"])
        by_category[r["category"]].append(r["amount"])
    sup_med = {k: median(v) for k, v in by_supplier.items()}
    cat_med = {k: median(v) for k, v in by_category.items()}
    names = list(FEATURES)
    X = []
    for r in rows:
        n = len(by_supplier[r["supplier_id"]])
        # leave-one-out style: with few invoices the supplier median is unreliable
        vs_sup = r["amount"] / sup_med[r["supplier_id"]] if n >= 3 else 1.0
        X.append(
            [
                math.log(max(vs_sup, 1e-6)),
                math.log(max(r["amount"] / cat_med[r["category"]], 1e-6)),
                math.log1p(r["amount"]),
                math.log1p(n),
                1.0 if r["amount"] >= 10_000 and r["amount"] % 10_000 == 0 else 0.0,
                1.0 if r["received_at"].weekday() >= 5 else 0.0,
            ]
        )
    return np.asarray(X), names


def _explain(
    x: np.ndarray,
    med: np.ndarray,
    mad: np.ndarray,
    names: list[str],
    amount_ratio: float,
    category_ratio: float,
) -> dict:
    z = (x - med) / mad
    top = np.argsort(-np.abs(z))[:3]
    drivers = []
    for i in top:
        name = names[i]
        if name == "amount_vs_supplier":
            text_ = f"{amount_ratio:.1f}x this supplier's typical invoice"
        elif name == "amount_vs_category":
            text_ = f"{category_ratio:.1f}x the typical invoice in this category"
        else:
            text_ = FEATURES[name]
        drivers.append({"feature": name, "robust_z": round(float(z[i]), 1), "meaning": text_})
    return {
        "reason": "Unusual compared with other invoices: " + "; ".join(d["meaning"] for d in drivers[:2]),
        "drivers": drivers,
        "model": "IsolationForest",
    }


def detect(db: Session, params: dict) -> list[tuple]:
    rows = _load(db)
    if len(rows) < int(params.get("min_invoices", 200)):
        return []  # too little data for a meaningful model (e.g. the 8-invoice case-study sample)
    X, names = _features(rows)
    model = IsolationForest(
        n_estimators=300, contamination=float(params.get("contamination", 0.01)), random_state=42
    )
    model.fit(X)
    raw = -model.score_samples(X)  # higher = more anomalous
    pred = model.predict(X)
    lo, hi = float(np.min(raw)), float(np.max(raw))
    med = np.median(X, axis=0)
    mad = np.median(np.abs(X - med), axis=0) * 1.4826
    mad[mad == 0] = 1.0

    out = []
    for r, x, p, s in zip(rows, X, pred, raw, strict=True):
        if p != -1:
            continue
        score = int(50 + 45 * (s - lo) / (hi - lo or 1))
        out.append(
            (
                "INVOICE",
                r["id"],
                r["supplier_id"],
                score,
                _explain(x, med, mad, names, math.exp(x[0]), math.exp(x[1])),
            )
        )
    return out
