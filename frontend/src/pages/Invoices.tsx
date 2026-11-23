import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/Layout";
import { TermsRuler } from "../components/TermsRuler";
import { Button, Empty, Loading, Panel, Segmented, StatusBadge, SupplierType } from "../components/ui";
import { CaptureInvoice } from "./SubmitInvoice";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { date, EXCEPTIONS, money } from "../lib/format";
import type { Invoice, Page } from "../lib/types";

type View = "all" | "mine" | "overdue" | "exceptions" | "open";

export function Invoices() {
  const { user, can } = useAuth();
  const supplier = user?.role === "SUPPLIER";
  const [params, setParams] = useSearchParams();
  const view = (params.get("view") as View) ?? (can("APPROVER") ? "mine" : "all");
  const [capturing, setCapturing] = useState(false);

  const q = useQuery({
    queryKey: ["invoices", view],
    queryFn: () =>
      api<Page<Invoice>>("/invoices", {
        params: {
          overdue: view === "overdue" ? true : undefined,
          assigned_to_me: view === "mine" ? true : undefined,
          status: view === "exceptions" ? "EXCEPTION" : undefined,
          sort: view === "all" || view === "open" ? "days_desc" : undefined,
        },
      }),
  });
  const items = (q.data?.items ?? []).filter((i) => (view === "open" ? i.status !== "PAID" && i.status !== "REJECTED" : true));

  const views: { value: View; label: string }[] = supplier
    ? [{ value: "all", label: "All" }, { value: "open", label: "Not yet paid" }]
    : [
        ...(can("APPROVER", "FINANCE_OFFICER", "MANAGER") ? [{ value: "mine" as View, label: "Waiting on me" }] : []),
        { value: "all", label: "All" },
        { value: "overdue", label: "Past terms" },
        { value: "exceptions", label: "Exceptions" },
      ];

  return (
    <>
      <PageHeader
        title={supplier ? "My invoices" : "Invoices"}
        intro={
          supplier
            ? "Where each invoice is, who is handling it, and how it sits against 30-day payment terms."
            : "Every invoice has one accountable owner. The ruler shows days outstanding against 30-day terms."
        }
        action={
          <div className="flex flex-wrap items-center gap-3">
            <Segmented ariaLabel="Filter invoices" value={view} options={views} onChange={(v) => setParams({ view: v })} />
            {can("FINANCE_OFFICER", "ADMIN") && <Button onClick={() => setCapturing(true)}>Capture an invoice</Button>}
            {supplier && <Link to="/submit"><Button>Submit an invoice</Button></Link>}
          </div>
        }
      />
      <Panel>
        {q.isLoading ? (
          <Loading what="Loading invoices" />
        ) : items.length === 0 ? (
          <Empty title={view === "mine" ? "Nothing is waiting on you" : "No invoices here"}>
            {view === "mine" ? "Invoices routed to you for approval will appear here." : "Try another filter."}
          </Empty>
        ) : (
          <div className="-mx-4 -my-4 overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead className="border-b border-line-soft text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Invoice</th>
                  {!supplier && <th className="px-4 py-2.5 font-medium">Supplier</th>}
                  <th className="px-4 py-2.5 text-right font-medium">Amount</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="w-56 px-4 py-2.5 font-medium">Payment terms</th>
                  <th className="px-4 py-2.5 font-medium">With</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {items.map((i) => (
                  <tr key={i.id} className="hover:bg-paper/60">
                    <td className="px-4 py-3">
                      <Link to={`/invoices/${i.id}`} className="font-semibold text-ink hover:text-large hover:underline">{i.invoice_number}</Link>
                      <div className="text-xs text-muted">{i.po_number ?? "No PO"} · received {date(i.received_at)}</div>
                    </td>
                    {!supplier && (
                      <td className="px-4 py-3">
                        <div className="font-medium">{i.supplier.legal_name}</div>
                        <SupplierType type={i.supplier.supplier_type} />
                      </td>
                    )}
                    <td className="px-4 py-3 text-right font-semibold">{money(i.amount)}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={i.status} />
                      {i.exceptions[0] && <div className="mt-1 max-w-56 text-xs text-bad">{EXCEPTIONS[i.exceptions[0]] ?? i.exceptions[0]}</div>}
                    </td>
                    <td className="px-4 py-3"><TermsRuler days={i.days_outstanding} state={i.sla_state} /></td>
                    <td className="px-4 py-3 text-muted">{i.current_owner?.full_name ?? (i.status === "PAID" ? "Done" : <span className="font-semibold text-bad">Nobody</span>)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {capturing && <CaptureInvoice onClose={() => setCapturing(false)} />}
    </>
  );
}
