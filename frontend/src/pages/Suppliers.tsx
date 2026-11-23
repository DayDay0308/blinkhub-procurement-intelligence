import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState, type FormEvent } from "react";
import { PageHeader } from "../components/Layout";
import { Button, Empty, ErrorNote, Field, inputCls, searchCls, Loading, Modal, Panel, Segmented, SupplierType } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { date, plural, PROVINCES } from "../lib/format";
import type { Scorecard } from "../lib/types";

const KPI_LABEL: Record<keyof Scorecard["kpis"], string> = {
  delivery_reliability: "Delivery on time",
  invoice_accuracy: "Invoice accuracy",
  compliance: "Compliance documents",
  risk_record: "Risk record",
  price_competitiveness: "Price vs market",
};

function gradeTone(g: string) {
  return g === "A" || g === "B" ? "text-good" : g === "C" ? "text-warn" : g === "N/A" ? "text-muted" : "text-bad";
}

const KPI_SHORT: Record<keyof Scorecard["kpis"], string> = {
  delivery_reliability: "Delivery", invoice_accuracy: "Invoices", compliance: "Compliance", risk_record: "Risk", price_competitiveness: "Price",
};

/** One line of five small KPI meters, for dense lists. */
export function KpiStrip({ card }: { card: Scorecard }) {
  return (
    <ul className="grid grid-cols-5 gap-3">
      {(Object.keys(KPI_SHORT) as (keyof Scorecard["kpis"])[]).map((k) => {
        const v = card.kpis[k];
        return (
          <li key={k} className="text-xs" title={`${KPI_LABEL[k]}: ${v == null ? "not measured" : Math.round(v)}`}>
            <div className="truncate text-muted">{KPI_SHORT[k]}</div>
            <div className="mt-1 flex items-center gap-1.5">
              <div className="h-1.5 flex-1 rounded-full bg-line-soft">{v != null && <div className={clsx("h-1.5 rounded-full", v >= 70 ? "bg-good" : v >= 50 ? "bg-warn" : "bg-bad")} style={{ width: `${v}%` }} />}</div>
              <span className="w-6 text-right font-medium">{v == null ? "n/a" : Math.round(v)}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function KpiBars({ card }: { card: Scorecard }) {
  return (
    <ul className="space-y-1.5">
      {(Object.keys(KPI_LABEL) as (keyof Scorecard["kpis"])[]).map((k) => {
        const v = card.kpis[k];
        return (
          <li key={k} className="grid grid-cols-[130px_1fr_32px] items-center gap-2 text-xs">
            <span className="text-muted">{KPI_LABEL[k]}</span>
            <div className="h-1.5 rounded-full bg-line-soft">{v != null && <div className={clsx("h-1.5 rounded-full", v >= 70 ? "bg-good" : v >= 50 ? "bg-warn" : "bg-bad")} style={{ width: `${v}%` }} />}</div>
            <span className="text-right font-medium">{v == null ? "n/a" : Math.round(v)}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function Suppliers() {
  const { can } = useAuth();
  const [type, setType] = useState<"" | "SMME" | "LARGE_ENTERPRISE">("");
  const [registering, setRegistering] = useState(false);
  const q = useQuery({
    queryKey: ["scorecards", type],
    queryFn: () => api<{ items: Scorecard[]; total: number }>("/scorecards", { params: { supplier_type: type || undefined, limit: 500 } }),
  });
  const [search, setSearch] = useState("");
  const items = (q.data?.items ?? []).filter((c) => !search || c.supplier.legal_name.toLowerCase().includes(search.toLowerCase()));

  return (
    <>
      <PageHeader
        title="Supplier performance"
        intro="Scored on delivery (30%), invoice accuracy (25%), compliance (20%), risk record (15%) and price (10%). Suppliers with no recent activity aren't graded."
        action={
          <div className="flex flex-wrap items-center gap-3">
            <Segmented ariaLabel="Supplier type" value={type} onChange={setType} options={[{ value: "", label: "All" }, { value: "SMME", label: "SMMEs" }, { value: "LARGE_ENTERPRISE", label: "Large" }]} />
            {can("PROCUREMENT_OFFICER", "ADMIN") && <Button onClick={() => setRegistering(true)}>Register a supplier</Button>}
          </div>
        }
      />
      <Panel title={q.data ? `${items.length} suppliers, best first` : undefined} action={<input className={`${searchCls} w-56`} placeholder="Search suppliers" aria-label="Search suppliers" value={search} onChange={(e) => setSearch(e.target.value)} />}>
        {q.isLoading ? <Loading /> : !items.length ? <Empty title="No suppliers match" /> : (
          <ul className="-my-4 divide-y divide-line-soft">
            {items.slice(0, 120).map((c) => (
              <li key={c.supplier.id} className="grid items-center gap-4 py-3 md:grid-cols-[48px_1.2fr_1.6fr_1fr]">
                <div className={clsx("text-3xl font-bold", gradeTone(c.grade))} aria-label={`Grade ${c.grade}`}>{c.grade}</div>
                <div className="min-w-0">
                  <div className="font-semibold">{c.supplier.legal_name}</div>
                  <div className="flex flex-wrap gap-x-3 text-xs text-muted"><SupplierType type={c.supplier.supplier_type} /><span>{PROVINCES[c.supplier.province] ?? c.supplier.province}</span><span>{c.supplier.bbbee_level ? `B-BBEE level ${c.supplier.bbbee_level}` : "No B-BBEE certificate"}</span></div>
                  <div className="mt-0.5 text-xs text-muted">{c.overall != null ? `Score ${c.overall.toFixed(0)} / 100` : "Not enough activity to score"}</div>
                </div>
                <KpiStrip card={c} />
                <div className="text-xs text-muted">
                  {plural(c.evidence.deliveries, "delivery", "deliveries")}{c.evidence.avg_days_late ? `, ${c.evidence.avg_days_late.toFixed(1)} days late on average` : ", all on time"}<br />
                  {plural(c.evidence.invoices, "invoice")} · {plural(c.evidence.open_flags, "open flag")}<br />
                  Tax clearance until {date(c.evidence.tax_clearance_expiry)}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      {registering && <RegisterSupplier onClose={() => setRegistering(false)} />}
    </>
  );
}

function RegisterSupplier({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ legal_name: "", registration_number: "", vat_number: "", csd_number: "", province: "GAUTENG", supplier_type: "SMME", bbbee_level: "", email: "" });
  const [similar, setSimilar] = useState<{ legal_name: string; similarity: number }[] | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: (ack: boolean) =>
      api<{ supplier_code: string }>("/suppliers", {
        body: { ...f, vat_number: f.vat_number || null, csd_number: f.csd_number || null, email: f.email || null, bbbee_level: f.bbbee_level ? +f.bbbee_level : null, acknowledge_similar: ack },
      }),
    onSuccess: (s) => { qc.invalidateQueries({ queryKey: ["scorecards"] }); setDone(s.supplier_code); },
    onError: (e) => {
      const d = e instanceof ApiError && e.status === 409 ? (e.details as { similar?: { legal_name: string; similarity: number }[] }) : null;
      setSimilar(d?.similar ?? null);
    },
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(false); };

  if (done) return (
    <Modal title="Supplier registered" onClose={onClose}>
      <p className="text-sm">{f.legal_name} is registered as <strong>{done}</strong> with status <strong>Pending</strong>. It can be used once its compliance documents are verified.</p>
      <div className="mt-5 flex justify-end"><Button onClick={onClose}>Done</Button></div>
    </Modal>
  );

  return (
    <Modal title="Register a supplier" onClose={onClose}>
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2"><Field label="Legal name"><input className={inputCls} required minLength={2} value={f.legal_name} onChange={set("legal_name")} /></Field></div>
        <Field label="CIPC registration number" hint="2019/123456/07"><input className={inputCls} required pattern="\d{4}/\d{6}/\d{2}" value={f.registration_number} onChange={set("registration_number")} /></Field>
        <Field label="VAT number" hint="10 digits starting with 4"><input className={inputCls} pattern="4\d{9}" value={f.vat_number} onChange={set("vat_number")} /></Field>
        <Field label="CSD number" hint="MAAA0000000"><input className={inputCls} pattern="MAAA\d{7}" value={f.csd_number} onChange={set("csd_number")} /></Field>
        <Field label="Province"><select className={inputCls} value={f.province} onChange={set("province")}>{Object.entries(PROVINCES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Type"><select className={inputCls} value={f.supplier_type} onChange={set("supplier_type")}><option value="SMME">SMME</option><option value="LARGE_ENTERPRISE">Large enterprise</option></select></Field>
        <Field label="B-BBEE level"><select className={inputCls} value={f.bbbee_level} onChange={set("bbbee_level")}><option value="">None</option>{[1, 2, 3, 4, 5, 6, 7, 8].map((n) => <option key={n} value={n}>Level {n}</option>)}</select></Field>
        <div className="sm:col-span-2"><Field label="Accounts email"><input className={inputCls} type="email" value={f.email} onChange={set("email")} /></Field></div>
        <div className="sm:col-span-2 space-y-3">
          {similar ? (
            <div className="rounded-md border border-warn/40 bg-attention p-3 text-sm">
              <p className="font-semibold">This may already be registered</p>
              <ul className="mt-1 list-disc pl-5">{similar.map((s) => <li key={s.legal_name}>{s.legal_name} ({Math.round(s.similarity * 100)}% similar name)</li>)}</ul>
              <p className="mt-2">Check these first. If it's a different business, register it anyway.</p>
            </div>
          ) : <ErrorNote error={m.error} />}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            {similar ? <Button type="button" onClick={() => m.mutate(true)} disabled={m.isPending}>Register anyway</Button> : <Button type="submit" disabled={m.isPending}>{m.isPending ? "Checking…" : "Register supplier"}</Button>}
          </div>
        </div>
      </form>
    </Modal>
  );
}
