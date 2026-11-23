"""Measure the risk engine against the planted-anomaly answer key (synthetic data only).

precision        = of the flags a rule raised on synthetic records, how many were the anomaly
                   type that rule targets
precision (any)  = also counting flags that landed on a different planted anomaly (a real
                   problem caught by another rule, e.g. a duplicate invoice paid with no PO)
recall           = of the planted anomalies of that type, how many the rule caught

Case-study records are excluded: they have no answer key.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

SQL = text("""
WITH scope AS (  -- flags on synthetic records only
  SELECT f.* FROM risk.flags f
  LEFT JOIN core.suppliers s ON s.id = f.supplier_id
  WHERE f.entity_type IN ('OPPORTUNITY', 'CATEGORY') OR s.supplier_code LIKE 'SYN-%'
),
flagged AS (
  SELECT f.rule_code, count(*) AS flags,
         count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM synthetic.anomaly_labels l
           WHERE l.anomaly_type = f.rule_code AND l.entity_type = f.entity_type AND l.entity_id = f.entity_id
         )) AS true_positives,
         count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM synthetic.anomaly_labels l
           WHERE l.anomaly_type <> f.rule_code AND l.entity_id = f.entity_id
         ) AND NOT EXISTS (
           SELECT 1 FROM synthetic.anomaly_labels l
           WHERE l.anomaly_type = f.rule_code AND l.entity_id = f.entity_id
         )) AS other_planted
  FROM scope f GROUP BY 1
),
planted AS (
  SELECT l.anomaly_type AS rule_code, count(*) AS planted,
         count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM risk.flags f
           WHERE f.rule_code = l.anomaly_type AND f.entity_type = l.entity_type AND f.entity_id = l.entity_id
         )) AS caught
  FROM synthetic.anomaly_labels l GROUP BY 1
)
SELECT r.code, r.name, coalesce(p.planted, 0) AS planted, coalesce(p.caught, 0) AS caught,
       coalesce(f.flags, 0) AS flags, coalesce(f.true_positives, 0) AS true_positives,
       coalesce(f.other_planted, 0) AS caught_other_planted
FROM risk.rules r
LEFT JOIN planted p ON p.rule_code = r.code
LEFT JOIN flagged f ON f.rule_code = r.code
ORDER BY r.code
""")


def evaluate(db: Session) -> dict:
    rows = db.execute(SQL).mappings().all()
    per_rule = []
    tot = {"planted": 0, "caught": 0, "flags": 0, "true_positives": 0, "caught_other_planted": 0}
    for r in rows:
        r = dict(r)
        r["precision"] = round(r["true_positives"] / r["flags"], 3) if r["flags"] else None
        r["precision_any"] = (
            round((r["true_positives"] + r["caught_other_planted"]) / r["flags"], 3) if r["flags"] else None
        )
        r["recall"] = round(r["caught"] / r["planted"], 3) if r["planted"] else None
        per_rule.append(r)
        for k in tot:
            tot[k] += r[k]
    return {
        "note": "Measured on synthetic demonstration data with planted anomalies. "
        "Not a measurement of MICS's real procurement.",
        "rules": per_rule,
        "overall": {
            **tot,
            "precision": round(tot["true_positives"] / tot["flags"], 3) if tot["flags"] else None,
            "precision_any": (
                round((tot["true_positives"] + tot["caught_other_planted"]) / tot["flags"], 3)
                if tot["flags"]
                else None
            ),
            "recall": round(tot["caught"] / tot["planted"], 3) if tot["planted"] else None,
        },
    }
