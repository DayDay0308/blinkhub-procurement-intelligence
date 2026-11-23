"""BlinkHub end-to-end demo check.

Runs the whole demo story against your running stack, the way real users would, and prints
PASS / FAIL for every step. Run it before every presentation.

    docker compose up -d          # wait ~1 minute after a fresh start
    python scripts/demo_check.py

Safe to run many times: each run submits one small, uniquely numbered invoice and pays it.
Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

PASSWORD = "Demo@2026!"
RESULTS: list[tuple[str, str, str]] = []  # (status, step, detail)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------- helpers
class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.tokens: dict[str, str] = {}

    def call(self, method: str, path: str, who: str | None = None, body: dict | None = None,
             form: dict | None = None, params: dict | None = None) -> tuple[int, object]:
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers, data = {}, None
        if who:
            headers["Authorization"] = f"Bearer {self.token(who)}"
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"null")
            except json.JSONDecodeError:
                return e.code, None

    def token(self, email: str) -> str:
        if email not in self.tokens:
            status, body = self.call("POST", "/api/v1/auth/login",
                                     form={"username": email, "password": PASSWORD})
            if status != 200:
                raise RuntimeError(f"login failed for {email}: {status} {body}")
            self.tokens[email] = body["access_token"]
        return self.tokens[email]


def step(name: str):
    """Decorator: run a check, record PASS/FAIL/SKIP with a short detail."""
    def wrap(fn):
        def run(*args, **kwargs):
            try:
                detail = fn(*args, **kwargs) or ""
                status = "SKIP" if str(detail).startswith("SKIP") else "PASS"
                RESULTS.append((status, name, str(detail).removeprefix("SKIP: ")))
            except AssertionError as e:
                RESULTS.append(("FAIL", name, str(e) or "assertion failed"))
            except Exception as e:  # noqa: BLE001 - report any error as a failed step
                RESULTS.append(("FAIL", name, f"{type(e).__name__}: {e}"))
            print(f"  [{RESULTS[-1][0]:^4}] {name}" + (f" - {RESULTS[-1][2]}" if RESULTS[-1][2] else ""))
        return run
    return wrap


def email_for(full_name: str) -> str:
    """Map a demo staff member's name to their login (approvers are routed automatically)."""
    fixed = {"Anele Approver": "approver@mics.demo", "Farid Finance": "finance@mics.demo",
             "Fikile Finance": "finance2@mics.demo", "Mpho Manager": "manager@mics.demo"}
    if full_name in fixed:
        return fixed[full_name]
    if full_name.endswith(" Approver"):
        dept = full_name.removesuffix(" Approver").lower().replace(" ", "")
        return f"approver.{dept}@mics.demo"
    raise AssertionError(f"unknown demo user {full_name!r}")


def psql(sql: str) -> str:
    out = subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-U", "blinkhub", "-d", "blinkhub",
                          "-tA", "-c", sql], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:200])
    return out.stdout.strip()


# --------------------------------------------------------------------------- checks
def run_checks(api: Api, use_docker: bool) -> None:
    MANAGER, FINANCE, AUDITOR = "manager@mics.demo", "finance@mics.demo", "auditor@mics.demo"
    PROCUREMENT, THUTO, UBUNTU = "procurement@mics.demo", "accounts@thutosupplies.demo", "accounts@ubuntucleaning.demo"
    state: dict = {}

    print("\n1. Platform")

    @step("API is up and the database is reachable")
    def _():
        status, body = api.call("GET", "/health")
        assert status == 200 and body["database"] == "ok", f"{status} {body}"
    _()

    @step("All demo roles can sign in")
    def _():
        roles = []
        for email in ["admin@mics.demo", PROCUREMENT, FINANCE, "approver@mics.demo", MANAGER, AUDITOR,
                      UBUNTU, THUTO]:
            status, me = api.call("GET", "/api/v1/auth/me", who=email)
            assert status == 200, f"{email}: {status}"
            roles.append(me["role"])
        return f"{len(roles)} accounts, roles: {', '.join(sorted(set(roles)))}"
    _()

    @step("Wrong password is rejected")
    def _():
        status, _ = api.call("POST", "/api/v1/auth/login", form={"username": MANAGER, "password": "wrong"})
        assert status == 401, status
    _()

    print("\n2. Case-study data (section 6 of the brief)")

    @step("8 case-study invoices loaded")
    def _():
        _, body = api.call("GET", "/api/v1/invoices", who=MANAGER)
        inv = {i["invoice_number"]: i for i in body["items"] if i["invoice_number"].startswith("INV00")}
        state["case_invoices"] = inv
        assert len(inv) == 8, f"found {len(inv)}"
        return f"{body['total']} invoices in total (incl. synthetic)"
    _()

    @step("5 case-study invoices overdue, worth R955,000")
    def _():
        _, body = api.call("GET", "/api/v1/invoices", who=MANAGER, params={"overdue": "true"})
        case = [i for i in body["items"] if i["invoice_number"].startswith("INV00")]
        total = sum(float(i["amount"]) for i in case)
        assert len(case) == 5 and total == 955_000, f"{len(case)} invoices, R{total:,.0f}"
        return "oldest: " + case[0]["invoice_number"] + f" ({case[0]['days_outstanding']} days)"
    _()

    @step("Supplier sees only its own invoices")
    def _():
        _, body = api.call("GET", "/api/v1/invoices", who=UBUNTU)
        names = {i["supplier"]["legal_name"] for i in body["items"]}
        assert names == {"Ubuntu Cleaning"}, names
        other = state["case_invoices"]["INV003"]["id"]  # Metro's invoice
        status, _ = api.call("GET", f"/api/v1/invoices/{other}", who=UBUNTU)
        assert status == 404, f"expected 404 for another supplier's invoice, got {status}"
    _()

    print("\n3. Invoice workflow (Problem 4)")
    run_id = time.strftime("%m%d%H%M%S")
    amount = round(100 + (int(time.time()) % 9000) / 100, 2)
    number = f"DEMO-{run_id}"

    @step(f"Thuto submits {number} (R{amount}) on PO010 -> waits for delivery")
    def _():
        status, inv = api.call("POST", "/api/v1/invoices", who=THUTO, body={
            "invoice_number": number, "po_number": "PO010", "amount": amount,
            "invoice_date": date.today().isoformat()})
        assert status == 201, f"{status} {inv}"
        # First run: no delivery yet. Later runs: earlier deliveries exist but don't cover this
        # invoice. Both mean "waiting for delivery evidence".
        waiting = {"AWAITING_GOODS_RECEIPT", "EXCEEDS_GOODS_RECEIVED"}
        assert inv["status"] == "EXCEPTION" and waiting & set(inv["exceptions"]), inv["exceptions"]
        assert inv["current_owner"], "invoice has no owner"
        state["inv"] = inv
        return f"owner: {inv['current_owner']['full_name']} ({inv['current_owner']['role']})"
    _()

    @step("Resubmitting the same number is blocked (409)")
    def _():
        assert "inv" in state, "previous step failed"
        status, _ = api.call("POST", "/api/v1/invoices", who=THUTO, body={
            "invoice_number": number.lower().replace("-", " "), "po_number": "PO010", "amount": amount,
            "invoice_date": date.today().isoformat()})
        assert status == 409, status
    _()

    @step("Procurement records delivery -> invoice routed to an approver")
    def _():
        assert "inv" in state, "previous step failed"
        # Receive whatever has been invoiced but not yet received on PO010 (covers invoices
        # left waiting by earlier runs too).
        _, pos = api.call("GET", "/api/v1/purchase-orders", who=PROCUREMENT)
        po = next(p for p in pos["items"] if p["po_number"] == "PO010")
        gap = round(float(po["invoiced_amount"]) - float(po["received_amount"]), 2)
        assert gap > 0, f"nothing to receive on PO010 (invoiced {po['invoiced_amount']}, received {po['received_amount']})"
        status, body = api.call("POST", "/api/v1/purchase-orders/PO010/goods-receipts", who=PROCUREMENT,
                                body={"amount_received": gap, "received_date": date.today().isoformat()})
        assert status == 201, f"{status} {body}"
        _, inv = api.call("GET", f"/api/v1/invoices/{state['inv']['id']}", who=THUTO)
        assert inv["status"] == "PENDING_APPROVAL", inv["status"]
        state["approver"] = email_for(inv["current_owner"]["full_name"])
        return f"routed to {inv['current_owner']['full_name']}"
    _()

    @step("Assigned approver approves")
    def _():
        assert "approver" in state, "previous step failed"
        status, inv = api.call("POST", f"/api/v1/invoices/{state['inv']['id']}/approve", who=state["approver"],
                               body={"comment": "Delivered in full (demo check)"})
        assert status == 200 and inv["status"] == "APPROVED", f"{status} {inv}"
    _()

    @step("Finance pays it; paying twice is impossible")
    def _():
        assert "approver" in state, "previous step failed"
        status, pay = api.call("POST", f"/api/v1/invoices/{state['inv']['id']}/pay", who=FINANCE)
        assert status == 200, f"{status} {pay}"
        again, _ = api.call("POST", f"/api/v1/invoices/{state['inv']['id']}/pay", who=FINANCE)
        assert again == 422, f"second payment returned {again}"
        return pay["reference"]
    _()

    @step("Supplier sees the full timeline and a 'paid' notification")
    def _():
        assert "approver" in state, "previous step failed"
        _, events = api.call("GET", f"/api/v1/invoices/{state['inv']['id']}/timeline", who=THUTO)
        actions = [e["action"] for e in events]
        assert actions[0] == "INVOICE_SUBMITTED" and actions[-1] == "INVOICE_PAID", actions
        _, notes = api.call("GET", "/api/v1/notifications", who=THUTO)
        assert any(n["kind"] == "INVOICE_PAID" and n["entity_id"] == state["inv"]["id"] for n in notes["items"])
        return " -> ".join(a.removeprefix("INVOICE_").lower() for a in actions)
    _()

    @step("Deadline (SLA) check alerts managers, SMMEs tagged as priority")
    def _():
        status, result = api.call("POST", "/api/v1/jobs/sla-check", who=MANAGER)
        assert status == 200 and result.get("BREACHED", 0) >= 5, result
        _, notes = api.call("GET", "/api/v1/notifications", who=MANAGER)
        titles = [n["title"] for n in notes["items"] if n["kind"] == "SLA_BREACHED"]
        assert any(t.startswith("[SMME priority]") for t in titles), "no SMME-priority alert"
        return f"{result['BREACHED']} breached invoices"
    _()

    print("\n4. Risk engine (Problem 6)")

    @step("Risk scan runs")
    def _():
        status, result = api.call("POST", "/api/v1/risk/run", who=MANAGER)
        assert status == 200, result
        return f"{result['total']} flags in {result['duration_ms']} ms"
    _()

    @step("Case-study duplicates flagged (INV008 ~ INV002, INV006 ~ paid INV001)")
    def _():
        items = []  # open flags plus any you already closed during a Swagger demo
        for status in (None, "CONFIRMED", "DISMISSED"):
            params = {"rule_code": "DUP_INVOICE", "limit": 500, **({"status": status} if status else {})}
            items += api.call("GET", "/api/v1/risk/flags", who=AUDITOR, params=params)[1]["items"]
        ids = {v["id"]: k for k, v in state["case_invoices"].items()}
        found = {ids[f["entity_id"]]: f["explanation"]["matching_invoice"] for f in items if f["entity_id"] in ids}
        assert found.get("INV008") == "INV002", found
        assert found.get("INV006") == "INV001", found
    _()

    @step("Suppliers cannot see risk flags (403)")
    def _():
        status, _ = api.call("GET", "/api/v1/risk/flags", who=UBUNTU)
        assert status == 403, status
    _()

    @step("Closing a flag requires a written note")
    def _():
        _, body = api.call("GET", "/api/v1/risk/flags", who=AUDITOR, params={"limit": 1})
        if not body["items"]:
            return "SKIP: no open flags"
        flag_id = body["items"][0]["id"]
        status, _ = api.call("POST", f"/api/v1/risk/flags/{flag_id}/status", who=AUDITOR,
                             body={"status": "DISMISSED"})
        assert status == 422, f"closing without a note returned {status}"
    _()

    @step("Detection rates on the planted anomalies")
    def _():
        _, ev = api.call("GET", "/api/v1/risk/evaluation", who=AUDITOR)
        o = ev["overall"]
        if not o["planted"]:
            return "SKIP: synthetic year not loaded (SEED_SYNTHETIC=false)"
        assert o["recall"] >= 0.95 and o["precision"] >= 0.85, o
        return f"recall {o['recall']:.1%}, precision {o['precision']:.1%} ({o['caught']}/{o['planted']} caught)"
    _()

    print("\n5. Supplier performance")

    @step("Scorecards computed; a supplier can view its own")
    def _():
        _, body = api.call("GET", "/api/v1/scorecards", who=MANAGER, params={"limit": 500})
        scored = [c for c in body["items"] if c["status"] == "SCORED"]
        assert scored, "no scored suppliers"
        ubuntu = next(c for c in body["items"] if c["supplier"]["legal_name"] == "Ubuntu Cleaning")
        status, _ = api.call("GET", f"/api/v1/suppliers/{ubuntu['supplier']['id']}/scorecard", who=UBUNTU)
        assert status == 200, status
        grades = {}
        for c in scored:
            grades[c["grade"]] = grades.get(c["grade"], 0) + 1
        return f"{len(scored)} suppliers scored, grades {dict(sorted(grades.items()))}"
    _()

    print("\n6. Analytics (dbt marts for Power BI) and services")
    if not use_docker:
        RESULTS.append(("SKIP", "Analytics and container checks", "Docker CLI not found"))
        print("  [SKIP] Analytics and container checks - Docker CLI not found")
        return

    @step("All 6 containers are running")
    def _():
        out = subprocess.run(["docker", "compose", "ps", "--services", "--filter", "status=running"],
                             capture_output=True, text=True, timeout=60).stdout.split()
        missing = {"db", "redis", "api", "worker", "dagster", "web"} - set(out)
        assert not missing, f"not running: {', '.join(sorted(missing))}"
    _()

    @step("dbt built the analytics marts")
    def _():
        n = int(psql("select count(*) from information_schema.tables where table_schema = 'analytics'"))
        assert n >= 10, f"only {n} tables in analytics (has the dagster service finished building?)"
        return f"{n} tables in schema analytics"
    _()

    @step("Power BI check numbers: R4,027,000 spend, 16.3% SMME (case study)")
    def _():
        total, share = psql(
            "select sum(po_amount), round(100 * sum(po_amount) filter (where is_smme) / sum(po_amount), 1) "
            "from analytics.fct_purchase_orders where data_source = 'CASE_STUDY'").split("|")
        assert float(total) == 4_027_000 and float(share) == 16.3, f"R{float(total):,.0f}, {share}%"
    _()

    @step("Dagster UI is up (http://localhost:3000)")
    def _():
        with urllib.request.urlopen("http://localhost:3000/server_info", timeout=15) as r:
            info = json.loads(r.read())
        return f"Dagster {info['dagster_version']}"
    _()

    @step("Web app is up and reaches the API through nginx (http://localhost:8080)")
    def _():
        web = os.environ.get("WEB_URL", "http://localhost:8080")
        with urllib.request.urlopen(web + "/", timeout=15) as r:
            assert b'id="root"' in r.read(), "web page did not load"
        with urllib.request.urlopen(web + "/login", timeout=15) as r:
            assert r.status == 200, "deep links are not served (SPA fallback)"
        req = urllib.request.Request(web + "/api/v1/auth/login", method="POST",
                                     data=urllib.parse.urlencode({"username": "manager@mics.demo", "password": PASSWORD}).encode())
        with urllib.request.urlopen(req, timeout=15) as r:
            assert "access_token" in json.loads(r.read()), "sign-in through the web proxy failed"
        return "page, deep link and /api proxy OK"
    _()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--no-docker", action="store_true", help="skip checks that need the Docker CLI")
    args = parser.parse_args()

    print("BlinkHub demo check against", args.base_url)
    api = Api(args.base_url)
    try:
        urllib.request.urlopen(args.base_url + "/health", timeout=10)
    except Exception as e:  # noqa: BLE001
        print(f"\nCannot reach the API at {args.base_url} ({e}).\nStart it with: docker compose up -d")
        return 2

    run_checks(api, use_docker=not args.no_docker and shutil.which("docker") is not None)

    passed = sum(1 for s, *_ in RESULTS if s == "PASS")
    failed = [(n, d) for s, n, d in RESULTS if s == "FAIL"]
    skipped = sum(1 for s, *_ in RESULTS if s == "SKIP")
    print(f"\n{'=' * 60}\n{passed} passed, {len(failed)} failed, {skipped} skipped")
    if failed:
        print("\nFailed steps:")
        for n, d in failed:
            print(f"  - {n}: {d}")
        print("\nTip: after installing a new phase, run `docker compose down -v` then `docker compose up --build`.")
        return 1
    print("All good: the demo is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
