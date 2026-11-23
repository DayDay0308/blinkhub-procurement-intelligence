import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/Layout";
import { Button, ErrorNote, Field, inputCls, Modal, Panel } from "../components/ui";
import { api } from "../lib/api";
import type { Invoice, Page } from "../lib/types";

interface Draft {
  invoice_number: string;
  po_number: string;
  amount: string;
  vat_amount: string;
  invoice_date: string;
  supplier_id?: string;
}

const today = () => new Date().toISOString().slice(0, 10);

function InvoiceFields({ d, set, staff }: { d: Draft; set: (d: Draft) => void; staff?: boolean }) {
  const suppliers = useQuery({
    queryKey: ["suppliers", "active"],
    queryFn: () => api<Page<{ id: string; legal_name: string; supplier_code: string }>>("/suppliers", { params: { status: "ACTIVE", limit: 200 } }),
    enabled: Boolean(staff),
  });
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {staff && (
        <div className="sm:col-span-2">
          <Field label="Supplier">
            <select className={inputCls} required value={d.supplier_id ?? ""} onChange={(e) => set({ ...d, supplier_id: e.target.value })}>
              <option value="" disabled>Choose a supplier</option>
              {suppliers.data?.items.map((s) => <option key={s.id} value={s.id}>{s.legal_name} ({s.supplier_code})</option>)}
            </select>
          </Field>
        </div>
      )}
      <Field label="Invoice number"><input className={inputCls} required value={d.invoice_number} onChange={(e) => set({ ...d, invoice_number: e.target.value })} /></Field>
      <Field label="Purchase order number" hint="Quote it so the invoice can be matched and paid on time.">
        <input className={inputCls} placeholder="PO010" value={d.po_number} onChange={(e) => set({ ...d, po_number: e.target.value.toUpperCase() })} />
      </Field>
      <Field label="Amount including VAT (R)"><input className={inputCls} required inputMode="decimal" type="number" min="0.01" step="0.01" value={d.amount} onChange={(e) => set({ ...d, amount: e.target.value })} /></Field>
      <Field label="VAT (R)"><input className={inputCls} inputMode="decimal" type="number" min="0" step="0.01" value={d.vat_amount} onChange={(e) => set({ ...d, vat_amount: e.target.value })} /></Field>
      <Field label="Invoice date"><input className={inputCls} required type="date" max={today()} value={d.invoice_date} onChange={(e) => set({ ...d, invoice_date: e.target.value })} /></Field>
    </div>
  );
}

const blank = (): Draft => ({ invoice_number: "", po_number: "", amount: "", vat_amount: "0", invoice_date: today() });
const body = (d: Draft) => ({ ...d, po_number: d.po_number || null, vat_amount: d.vat_amount || "0" });

/** Supplier portal: submit an invoice. */
export function SubmitInvoice() {
  const [d, set] = useState<Draft>(blank);
  const nav = useNavigate();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => api<Invoice>("/invoices", { body: body(d) }),
    onSuccess: (inv) => { qc.invalidateQueries({ queryKey: ["invoices"] }); nav(`/invoices/${inv.id}`); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <>
      <PageHeader title="Submit an invoice" intro="The 30-day payment clock starts when we receive it. You can follow its progress from My invoices." />
      <Panel className="max-w-2xl">
        <form onSubmit={submit} className="space-y-5">
          <InvoiceFields d={d} set={set} />
          <ErrorNote error={m.error} />
          <Button type="submit" disabled={m.isPending}>{m.isPending ? "Submitting…" : "Submit invoice"}</Button>
        </form>
      </Panel>
    </>
  );
}

/** Finance: capture an invoice that arrived by email (the case study's main intake channel). */
export function CaptureInvoice({ onClose }: { onClose: () => void }) {
  const [d, set] = useState<Draft>(blank);
  const nav = useNavigate();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => api<Invoice>("/invoices", { body: body(d) }),
    onSuccess: (inv) => { qc.invalidateQueries({ queryKey: ["invoices"] }); nav(`/invoices/${inv.id}`); },
  });
  return (
    <Modal title="Capture an emailed invoice" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); m.mutate(); }} className="space-y-5">
        <InvoiceFields d={d} set={set} staff />
        <ErrorNote error={m.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={m.isPending}>{m.isPending ? "Capturing…" : "Capture invoice"}</Button>
        </div>
      </form>
    </Modal>
  );
}
