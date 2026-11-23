import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ReviewDialog, requirementDetail, STATE, StateBadge, SupplierDocumentsView } from "../components/Documents";
import { PageHeader } from "../components/Layout";
import { Button, Empty, Loading, Modal, Panel, Segmented, Stat, SupplierType, searchCls } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { money, moneyShort, plural } from "../lib/format";
import type { ComplianceItem, ComplianceOverview, ComplianceState } from "../lib/types";

type Filter = "attention" | ComplianceState | "ALL";

export function Compliance() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["compliance"], queryFn: () => api<ComplianceOverview>("/compliance/overview") });
  const [filter, setFilter] = useState<Filter>("attention");
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<ComplianceItem | null>(null);
  const [review, setReview] = useState<{ item: ComplianceItem; documentId: string } | null>(null);
  const job = useMutation({
    mutationFn: () => api<Record<string, number>>("/jobs/compliance-check", { method: "POST" }),
    onSuccess: () => ["compliance", "notifications"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })),
  });

  if (!q.data) return <Loading what="Checking supplier documents" />;
  const d = q.data;
  const reviewer = can("PROCUREMENT_OFFICER", "ADMIN");
  const toReview = d.items.flatMap((i) => i.requirements.filter((r) => r.pending_document_id).map((r) => ({ item: i, r })));
  const items = d.items
    .filter((i) => (filter === "ALL" ? true : filter === "attention" ? i.state !== "VALID" : i.state === filter))
    .filter((i) => !search || i.supplier.legal_name.toLowerCase().includes(search.toLowerCase()));

  return (
    <>
      <PageHeader
        title="Supplier compliance"
        intro={`Every active supplier needs a valid tax clearance and a B-BBEE certificate or affidavit. Certificates expiring within ${d.warning_days} days are flagged so renewals arrive in time. Reminders go out every morning at 06:00.`}
        action={can("PROCUREMENT_OFFICER", "MANAGER", "ADMIN") && (
          <Button variant="secondary" onClick={() => job.mutate()} disabled={job.isPending}>{job.isPending ? "Checking…" : "Run the check now"}</Button>
        )}
      />
      {job.data && (
        <p role="status" className="mb-4 rounded-md border border-line bg-surface px-3 py-2 text-sm">
          Check complete: {plural(job.data.documents_expired, "document")} marked expired; reminders sent for {job.data.reminders_expiring} expiring, {job.data.reminders_expired} expired and {job.data.reminders_missing} missing documents. Reminders already sent aren't repeated.
        </p>
      )}

      <div className="mb-5 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
        {(["EXPIRED", "MISSING", "EXPIRING", "VALID"] as ComplianceState[]).map((s) => (
          <button key={s} onClick={() => setFilter(s)} aria-pressed={filter === s} className={`p-4 text-left hover:bg-paper ${filter === s ? "bg-paper" : "bg-surface"}`}>
            <Stat label={STATE[s].text} value={d.by_state[s]} tone={s === "EXPIRED" || s === "MISSING" ? (d.by_state[s] ? "bad" : undefined) : undefined} sub="suppliers" />
          </button>
        ))}
        <div className="bg-surface p-4"><Stat label="Documents to check" value={d.awaiting_verification} sub="uploaded, not yet verified" /></div>
        <div className="bg-surface p-4"><Stat label="Paid to non-compliant" value={moneyShort(d.paid_to_non_compliant_90_days)} tone={+d.paid_to_non_compliant_90_days ? "bad" : undefined} sub="last 90 days" /></div>
      </div>

      {reviewer && toReview.length > 0 && (
        <Panel title={`Waiting for you to check (${toReview.length})`} className="mb-5">
          <ul className="-mx-4 -my-4 max-h-96 divide-y divide-line-soft overflow-y-auto px-4">
            {toReview.map(({ item, r }) => (
              <li key={r.pending_document_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <div className="font-semibold">{item.supplier.legal_name}</div>
                  <div className="text-sm text-muted">{r.label}{r.state === "EXPIRING" ? `: renewal for one that ${requirementDetail(r).toLowerCase().split(" ·")[0]}` : ""}</div>
                </div>
                <Button onClick={() => setReview({ item, documentId: r.pending_document_id! })}>Check document</Button>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel
        title={`${plural(items.length, "supplier")}${filter === "attention" ? " needing attention" : ""}`}
        action={
          <div className="flex flex-wrap items-center gap-3">
            <input className={`${searchCls} w-52`} placeholder="Search suppliers" aria-label="Search suppliers" value={search} onChange={(e) => setSearch(e.target.value)} />
            <Segmented ariaLabel="Show" value={filter === "attention" || filter === "ALL" ? filter : "attention"} onChange={setFilter} options={[{ value: "attention", label: "Needs attention" }, { value: "ALL", label: "All" }]} />
          </div>
        }
      >
        {items.length === 0 ? <Empty title="Nothing here">Every supplier in this view has valid documents.</Empty> : (
          <div className="-m-4 overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead className="border-b border-line-soft text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Supplier</th>
                  <th className="px-4 py-2.5 font-medium">Tax clearance</th>
                  <th className="px-4 py-2.5 font-medium">B-BBEE</th>
                  <th className="px-4 py-2.5 text-right font-medium">Paid in last 90 days</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {items.slice(0, 150).map((i) => (
                  <tr key={i.supplier.id} className="cursor-pointer hover:bg-paper/60" onClick={() => setOpen(i)}>
                    <td className="px-4 py-3">
                      <button className="text-left font-semibold hover:text-large hover:underline">{i.supplier.legal_name}</button>
                      <div className="flex gap-3 text-xs text-muted"><SupplierType type={i.supplier.supplier_type} /><span>{i.supplier.supplier_code}</span></div>
                    </td>
                    {(["TAX_CLEARANCE", "BBBEE"] as const).map((key) => {
                      const r = i.requirements.find((x) => x.requirement === key);
                      return (
                        <td key={key} className="px-4 py-3">
                          {r && <><StateBadge state={r.state} /><div className="mt-1 text-xs text-muted">{requirementDetail(r)}</div></>}
                        </td>
                      );
                    })}
                    <td className={`px-4 py-3 text-right font-medium ${+i.paid_last_90_days && (i.state === "EXPIRED" || i.state === "MISSING") ? "text-bad" : ""}`}>{money(i.paid_last_90_days)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {items.length > 150 && <p className="px-4 py-3 text-xs text-muted">Showing the first 150 of {items.length}. Search to narrow down.</p>}
          </div>
        )}
      </Panel>

      {open && (
        <Modal wide title={`${open.supplier.legal_name}: compliance documents`} onClose={() => setOpen(null)}>
          <SupplierDocumentsView supplierId={open.supplier.id} canUpload={reviewer} />
        </Modal>
      )}
      {review && <ReviewDialog supplierId={review.item.supplier.id} supplierName={review.item.supplier.legal_name} documentId={review.documentId} onClose={() => setReview(null)} />}
    </>
  );
}

/** Supplier portal. */
export function MyDocuments() {
  const { user } = useAuth();
  if (!user?.supplier_id) return null;
  return (
    <>
      <PageHeader title="My documents" intro="MICS needs a valid tax clearance and B-BBEE certificate (or affidavit) to keep paying you without delays. We'll remind you 30 days before anything expires." />
      <SupplierDocumentsView supplierId={user.supplier_id} canUpload />
    </>
  );
}
