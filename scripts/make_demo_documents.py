"""Generate fictional compliance documents for testing uploads (and, in Phase 6, document AI).

    uv run --with reportlab python scripts/make_demo_documents.py

Every page is watermarked DEMONSTRATION ONLY: these are not real certificates and use no
official logos, emblems or certificate numbers.
"""

from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / "demo-documents"
INK = HexColor("#1f2a44")
TODAY = date.today()


def page(path: Path, title: str, issuer: str, rows: list[tuple[str, str]]) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFillColor(INK)
    c.rect(0, h - 90, w, 90, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(40, h - 50, title)
    c.setFont("Helvetica", 10)
    c.drawString(40, h - 70, f"Issued by: {issuer} (fictional, for demonstration)")

    c.setFillColor(INK)
    y = h - 140
    for k, v in rows:
        c.setFont("Helvetica", 10)
        c.drawString(40, y, k)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(220, y, v)
        y -= 26

    c.saveState()
    c.setFillColor(Color(0.78, 0.21, 0.18, alpha=0.18))
    c.setFont("Helvetica-Bold", 52)
    c.translate(w / 2, h / 2 - 80)
    c.rotate(35)
    c.drawCentredString(0, 0, "DEMONSTRATION ONLY")
    c.restoreState()
    c.setFont("Helvetica", 8)
    c.drawString(40, 30, "Generated for the BlinkHub Procurement Innovation Challenge prototype. Not a real certificate.")
    c.save()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    issued = TODAY - timedelta(days=3)
    page(
        OUT / "Thuto_Supplies_BBBEE_Certificate_DEMO.pdf",
        "B-BBEE Verification Certificate",
        "Demo Verification Agency",
        [
            ("Entity", "Thuto Supplies"),
            ("Registration number", "2018/402233/07"),
            ("B-BBEE status level", "Level 1 (135% procurement recognition)"),
            ("Enterprise type", "EME"),
            ("Black ownership", "100%"),
            ("Date of issue", f"{issued:%d %B %Y}"),
            ("Expiry date", f"{issued + timedelta(days=365):%d %B %Y}"),
            ("Certificate number", "DEMO-BEE-0001"),
        ],
    )
    page(
        OUT / "Thuto_Supplies_Tax_Compliance_DEMO.pdf",
        "Tax Compliance Status",
        "Demo Revenue Office",
        [
            ("Taxpayer", "Thuto Supplies"),
            ("Tax reference", "DEMO 0000000001"),
            ("Compliance status", "Compliant"),
            ("Date of issue", f"{issued:%d %B %Y}"),
            ("Expiry date", f"{issued + timedelta(days=365):%d %B %Y}"),
            ("PIN", "DEMO-PIN-0001"),
        ],
    )
    page(
        OUT / "Rapid_Transport_BBBEE_Affidavit_DEMO.pdf",
        "B-BBEE Sworn Affidavit (EME)",
        "Commissioner of Oaths (demo)",
        [
            ("Entity", "Rapid Transport"),
            ("Annual turnover", "Below R10 million"),
            ("Black ownership", "100%"),
            ("B-BBEE status level", "Level 1"),
            ("Date sworn", f"{issued:%d %B %Y}"),
            ("Valid until", f"{issued + timedelta(days=365):%d %B %Y}"),
        ],
    )
    print("Wrote", ", ".join(p.name for p in sorted(OUT.glob("*.pdf"))))


if __name__ == "__main__":
    main()
