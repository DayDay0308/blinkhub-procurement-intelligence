import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { PageHeader } from "../components/Layout";
import { Button, ErrorNote, Field, inputCls, searchCls, Loading, Modal, Panel, StatusBadge, SupplierType } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { money } from "../lib/format";
import type { Page, PurchaseOrder } from "../lib/types";

/** Two stacked progress lines: delivered and invoiced, each against the order value. */
function Progress({ po }: { po: PurchaseOrder }) {
  const total = +po.total_amount;
  const rows = [
    { label: "Delivered", v: +po.received_amount, cls: "bg-ink" },
    { label: "Invoiced", v: +po.invoiced_amount, cls: +po.invoiced_amount > +po.received_amount ? "bg-bad" : "bg-good" },
  ];
  return (
    <div className="space-y-1">
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[60px_1fr_72px] items-center gap-2 text-xs">
          <span className="text-muted">{r.label}</span>
          <div className="h-1.5 rounded-full bg-line-soft"><div className={`h-1.5 rounded-full ${r.cls}`} style={{ width: `${Math.min(1, r.v / total) * 100}%` }} /></div>
          <span className="text-right">{money(r.v)}</span>
        </div>
      ))}
    </div>
  );
}

export function PurchaseOrders() {
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["pos"], queryFn: () => api<Page<PurchaseOrder>>("/purchase-orders") });
  const [receiving, setReceiving] = useState<PurchaseOrder | null>(null);
  const [filter, setFilter] = useState("");
  const items = (q.data?.items ?? []).filter((p) => !filter || `${p.po_number} ${p.supplier.legal_name} ${p.department}`.toLowerCase().includes(filter.toLowerCase()));

  return (
    <>
      <PageHeader
        title="Purchase orders"
        intro="Delivery evidence is what lets an invoice match. When goods are recorded, invoices waiting on the order are re-checked straight away."
        action={<input className={`${searchCls} w-72`} placeholder="Search order, supplier, department" aria-label="Search purchase orders" value={filter} onChange={(e) => setFilter(e.target.value)} />}
      />
      <Panel>
        {q.isLoading ? <Loading /> : (
          <div className="-m-4 overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead className="border-b border-line-soft text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Order</th>
                  <th className="px-4 py-2.5 font-medium">Supplier</th>
                  <th className="px-4 py-2.5 font-medium">Department · category</th>
                  <th className="px-4 py-2.5 text-right font-medium">Value</th>
                  <th className="w-72 px-4 py-2.5 font-medium">Delivered and invoiced</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {items.slice(0, 200).map((p) => (
                  <tr key={p.id}>
                    <td className="px-4 py-3"><div className="font-semibold">{p.po_number}</div><StatusBadge status={p.status} /></td>
                    <td className="px-4 py-3"><div className="font-medium">{p.supplier.legal_name}</div><SupplierType type={p.supplier.supplier_type} /></td>
                    <td className="px-4 py-3 text-muted">{p.department}<div className="text-xs">{p.category}</div></td>
                    <td className="px-4 py-3 text-right font-semibold">{money(p.total_amount)}</td>
                    <td className="px-4 py-3"><Progress po={p} /></td>
                    <td className="px-4 py-3 text-right">
                      {can("PROCUREMENT_OFFICER", "ADMIN") && +p.received_amount < +p.total_amount && (
                        <Button variant="secondary" onClick={() => setReceiving(p)}>Record delivery</Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {items.length > 200 && <p className="px-4 py-3 text-xs text-muted">Showing the first 200 of {items.length}. Search to narrow down.</p>}
          </div>
        )}
      </Panel>
      {receiving && <ReceiveDialog po={receiving} onClose={() => setReceiving(null)} />}
    </>
  );
}

function ReceiveDialog({ po, onClose }: { po: PurchaseOrder; onClose: () => void }) {
  const outstanding = (+po.total_amount - +po.received_amount).toFixed(2);
  const [amount, setAmount] = useState(outstanding);
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => api(`/purchase-orders/${po.po_number}/goods-receipts`, { body: { amount_received: amount, received_date: day } }),
    onSuccess: () => {
      ["pos", "invoices", "overview"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onClose();
    },
  });
  return (
    <Modal title={`Record delivery for ${po.po_number}`} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); m.mutate(); }} className="space-y-4">
        <p className="text-sm text-muted">{po.supplier.legal_name}. {money(outstanding)} still to be delivered.</p>
        <Field label="Value received (R)"><input className={inputCls} type="number" min="0.01" step="0.01" max={outstanding} required value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Date received"><input className={inputCls} type="date" required value={day} onChange={(e) => setDay(e.target.value)} /></Field>
        <ErrorNote error={m.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={m.isPending}>{m.isPending ? "Recording…" : "Record delivery"}</Button>
        </div>
      </form>
    </Modal>
  );
}
