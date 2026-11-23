import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { TermsRuler } from "../components/TermsRuler";
import { Button, ErrorNote, Field, inputCls, Loading, Modal, Panel, StatusBadge, SupplierType } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { date, dateTime, EXCEPTIONS, label, money, ROLE_LABEL } from "../lib/format";
import type { Invoice, TimelineEvent } from "../lib/types";

type Action = "approve" | "reject" | "pay" | "link-po";

export function InvoiceDetail() {
  const { id } = useParams();
  const { user, can } = useAuth();
  const qc = useQueryClient();
  const inv = useQuery({ queryKey: ["invoice", id], queryFn: () => api<Invoice>(`/invoices/${id}`) });
  const tl = useQuery({ queryKey: ["invoice", id, "timeline"], queryFn: () => api<TimelineEvent[]>(`/invoices/${id}/timeline`) });
  const [action, setAction] = useState<Action | null>(null);

  if (!inv.data) return inv.error ? <ErrorNote error={inv.error} /> : <Loading what="Loading invoice" />;
  const i = inv.data;
  const mine = i.current_owner?.id === user?.id;
  const done = () => {
    setAction(null);
    qc.invalidateQueries({ queryKey: ["invoice", id] });
    qc.invalidateQueries({ queryKey: ["invoices"] });
    qc.invalidateQueries({ queryKey: ["overview"] });
  };

  const actions: { key: Action; label: string; show: boolean; variant?: "secondary" | "danger" }[] = [
    { key: "approve", label: "Approve", show: i.status === "PENDING_APPROVAL" && mine && can("APPROVER", "FINANCE_OFFICER", "MANAGER") },
    { key: "pay", label: "Release payment", show: i.status === "APPROVED" && can("FINANCE_OFFICER") },
    { key: "link-po", label: "Link a purchase order", show: !i.po_number && i.status !== "PAID" && i.status !== "REJECTED" && can("FINANCE_OFFICER", "PROCUREMENT_OFFICER", "ADMIN"), variant: "secondary" },
    { key: "reject", label: "Reject", show: ["PENDING_APPROVAL", "EXCEPTION", "RECEIVED"].includes(i.status) && (mine || can("FINANCE_OFFICER")) && can("APPROVER", "FINANCE_OFFICER", "MANAGER"), variant: "danger" },
  ];

  return (
    <>
      <Link to="/invoices" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" /> Invoices</Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">{i.invoice_number}</h1>
            <StatusBadge status={i.status} />
          </div>
          <p className="mt-1 text-muted">{i.supplier.legal_name} · <SupplierType type={i.supplier.supplier_type} /></p>
        </div>
        <div className="flex flex-wrap gap-2">
          {actions.filter((a) => a.show).map((a) => (
            <Button key={a.key} variant={a.variant} onClick={() => setAction(a.key)}>{a.label}</Button>
          ))}
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-5">
          <Panel title="Payment terms">
            <TermsRuler days={i.days_outstanding} state={i.sla_state} size="lg" />
            <p className="mt-3 text-sm text-muted">
              {i.status === "PAID"
                ? `Paid on ${date(i.paid_at)}.`
                : `Received ${date(i.received_at)}, due ${date(i.due_date)}. Reminders go out at day 20, the manager is alerted at day 25.`}
            </p>
          </Panel>

          {i.exceptions.length > 0 && (
            <Panel title="Why it can't be approved yet">
              <ul className="space-y-2 text-sm">
                {i.exceptions.map((e) => (
                  <li key={e} className="flex gap-2"><span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-bad" />{EXCEPTIONS[e] ?? label(e)}</li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title="History">
            {tl.data && tl.data.length === 0 ? (
              <p className="text-sm text-muted">Received {date(i.received_at)}. This demonstration record was generated without step-by-step history; invoices handled in the app record every step here.</p>
            ) : tl.data ? (
              <ol className="relative space-y-4 border-l border-line pl-5">
                {tl.data.map((e, n) => (
                  <li key={n} className="relative">
                    <span className="absolute -left-[25px] top-1.5 size-2 rounded-full bg-ink" />
                    <div className="text-sm font-semibold">{label(e.action)}{e.status && <span className="font-normal text-muted"> → {label(e.status)}</span>}</div>
                    <div className="text-xs text-muted">{dateTime(e.at)}{e.by_role && ` · ${ROLE_LABEL[e.by_role] ?? e.by_role}`}</div>
                    {e.note && <p className="mt-1 text-sm">{e.note}</p>}
                  </li>
                ))}
              </ol>
            ) : (
              <Loading />
            )}
          </Panel>
        </div>

        <Panel title="Details">
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 text-sm">
            <dt className="text-muted">Amount</dt><dd className="text-right font-semibold">{money(i.amount)}</dd>
            <dt className="text-muted">Purchase order</dt><dd className="text-right">{i.po_number ?? <span className="font-semibold text-bad">None quoted</span>}</dd>
            <dt className="text-muted">Invoice date</dt><dd className="text-right">{date(i.invoice_date)}</dd>
            <dt className="text-muted">Received</dt><dd className="text-right">{date(i.received_at)}</dd>
            <dt className="text-muted">Due</dt><dd className="text-right">{date(i.due_date)}</dd>
            <dt className="text-muted">Ageing</dt><dd className="text-right">{i.ageing_bucket} days</dd>
            <dt className="text-muted">Currently with</dt>
            <dd className="text-right">{i.current_owner ? <>{i.current_owner.full_name}<div className="text-xs text-muted">{ROLE_LABEL[i.current_owner.role]}</div></> : i.status === "PAID" ? "Done" : <span className="font-semibold text-bad">Nobody</span>}</dd>
          </dl>
        </Panel>
      </div>

      {action && <ActionDialog action={action} invoice={i} onClose={() => setAction(null)} onDone={done} />}
    </>
  );
}

function ActionDialog({ action, invoice, onClose, onDone }: { action: Action; invoice: Invoice; onClose: () => void; onDone: () => void }) {
  const [text, setText] = useState("");
  const m = useMutation({
    mutationFn: () =>
      api(`/invoices/${invoice.id}/${action}`, {
        method: "POST",
        body: action === "reject" ? { reason: text } : action === "link-po" ? { po_number: text } : action === "approve" ? { comment: text || null } : undefined,
      }),
    onSuccess: onDone,
  });
  const titles: Record<Action, string> = {
    approve: `Approve ${invoice.invoice_number}`,
    reject: `Reject ${invoice.invoice_number}`,
    pay: `Release payment for ${invoice.invoice_number}`,
    "link-po": `Link a purchase order to ${invoice.invoice_number}`,
  };
  return (
    <Modal title={titles[action]} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); m.mutate(); }} className="space-y-4">
        {action === "pay" && <p className="text-sm">Pay <strong>{money(invoice.amount)}</strong> to {invoice.supplier.legal_name}. The payment goes to the verified bank account on file; a bank detail change in the last 72 hours blocks it.</p>}
        {action === "approve" && <Field label="Comment (optional)"><textarea className={inputCls} rows={2} value={text} onChange={(e) => setText(e.target.value)} /></Field>}
        {action === "reject" && <Field label="Reason" hint="The supplier sees this. At least 5 characters."><textarea className={inputCls} rows={3} required minLength={5} value={text} onChange={(e) => setText(e.target.value)} /></Field>}
        {action === "link-po" && <Field label="Purchase order number" hint="e.g. PO010. The invoice is re-matched against the order and deliveries."><input className={inputCls} required value={text} onChange={(e) => setText(e.target.value.toUpperCase())} /></Field>}
        <ErrorNote error={m.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant={action === "reject" ? "danger" : "primary"} disabled={m.isPending}>
            {m.isPending ? "Working…" : action === "pay" ? "Release payment" : action === "link-po" ? "Link order" : action === "approve" ? "Approve" : "Reject invoice"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
