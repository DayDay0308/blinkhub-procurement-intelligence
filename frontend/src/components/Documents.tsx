import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock, FileText, Upload, XCircle } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, openFile } from "../lib/api";
import { useAuth } from "../lib/auth";
import { date, dateTime, label } from "../lib/format";
import type { ComplianceState, Requirement, SupplierDocument, SupplierDocuments } from "../lib/types";
import { Badge, Button, ErrorNote, Field, inputCls, Loading, Modal, Panel } from "./ui";

/** Status of one requirement: icon + words, never colour alone. */
export const STATE: Record<ComplianceState, { text: string; tone: "good" | "warn" | "bad" | "neutral"; icon: typeof CheckCircle2 }> = {
  EXPIRED: { text: "Expired", tone: "bad", icon: XCircle },
  MISSING: { text: "Missing", tone: "bad", icon: AlertTriangle },
  PENDING_VERIFICATION: { text: "Waiting for verification", tone: "neutral", icon: Clock },
  EXPIRING: { text: "Expiring soon", tone: "warn", icon: Clock },
  VALID: { text: "Valid", tone: "good", icon: CheckCircle2 },
};

export function StateBadge({ state }: { state: ComplianceState }) {
  const s = STATE[state];
  return <Badge tone={s.tone}><s.icon className="size-3.5" aria-hidden />{s.text}</Badge>;
}

/** "expires in 12 days", "expired 15 Nov 2026", "never received" */
export function requirementDetail(r: Requirement): string {
  if (r.state === "MISSING") return "Never received";
  if (r.state === "PENDING_VERIFICATION") return "Uploaded, being checked";
  if (r.state === "EXPIRED") return r.expiry_date ? `Expired ${date(r.expiry_date)}` : "Expired";
  if (r.days_left != null && r.state === "EXPIRING") return `Expires in ${r.days_left} ${r.days_left === 1 ? "day" : "days"}${r.pending_document_id ? " · renewal received" : ""}`;
  return r.expiry_date ? `Valid until ${date(r.expiry_date)}` : "Valid";
}

const DOC_TYPES = [
  { value: "TAX_CLEARANCE", label: "Tax clearance (SARS tax compliance status)" },
  { value: "BBBEE_CERTIFICATE", label: "B-BBEE certificate" },
  { value: "BBBEE_AFFIDAVIT", label: "B-BBEE sworn affidavit (EME or QSE)" },
  { value: "CSD_REPORT", label: "CSD registration report" },
  { value: "BANK_CONFIRMATION", label: "Bank confirmation letter" },
  { value: "COID_LETTER", label: "COID letter of good standing" },
];
export const docTypeLabel = (t: string) => DOC_TYPES.find((d) => d.value === t)?.label.replace(/ \(.*\)$/, "") ?? label(t);

const DOC_STATUS_TONE: Record<SupplierDocument["status"], "good" | "warn" | "bad" | "neutral"> = {
  VERIFIED: "good", UPLOADED: "neutral", EXTRACTED: "neutral", REJECTED: "bad", EXPIRED: "bad",
};

/** Requirements, history and upload for one supplier. Used by the supplier portal and by staff. */
export function SupplierDocumentsView({ supplierId, canUpload }: { supplierId: string; canUpload: boolean }) {
  const q = useQuery({ queryKey: ["documents", supplierId], queryFn: () => api<SupplierDocuments>(`/suppliers/${supplierId}/documents`) });
  const [uploading, setUploading] = useState<string | null>(null);
  const [openError, setOpenError] = useState<unknown>(null);
  if (!q.data) return q.error ? <ErrorNote error={q.error} /> : <Loading />;
  const d = q.data;

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2">
        {d.requirements.map((r) => (
          <div key={r.requirement} className="rounded-lg border border-line bg-surface p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold">{r.label}</div>
                <div className="mt-0.5 text-sm text-muted">{requirementDetail(r)}</div>
              </div>
              <StateBadge state={r.state} />
            </div>
            {canUpload && r.state !== "VALID" && r.state !== "PENDING_VERIFICATION" && !(r.state === "EXPIRING" && r.pending_document_id) && (
              <Button className="mt-3" variant="secondary" onClick={() => setUploading(r.requirement === "BBBEE" ? "BBBEE_CERTIFICATE" : "TAX_CLEARANCE")}>
                <Upload className="size-4" aria-hidden /> Upload {r.state === "MISSING" ? "document" : "renewal"}
              </Button>
            )}
          </div>
        ))}
      </div>

      <Panel title="Documents on file" action={canUpload && <Button variant="secondary" onClick={() => setUploading("TAX_CLEARANCE")}><Upload className="size-4" aria-hidden /> Upload a document</Button>}>
        <ErrorNote error={openError} />
        {d.documents.length === 0 ? <p className="text-sm text-muted">No documents yet.</p> : (
          <ul className="-my-4 divide-y divide-line-soft">
            {d.documents.map((doc) => (
              <li key={doc.id} className="grid items-center gap-x-4 gap-y-1 py-3 sm:grid-cols-[1fr_auto]">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <FileText className="size-4 text-muted" aria-hidden />
                    <span className="font-medium">{docTypeLabel(doc.doc_type)}</span>
                    <Badge tone={DOC_STATUS_TONE[doc.status]}>{doc.status === "UPLOADED" ? "Waiting for verification" : label(doc.status)}</Badge>
                  </div>
                  <div className="mt-0.5 text-xs text-muted">
                    {doc.expiry_date ? `${doc.status === "UPLOADED" ? "Stated expiry" : "Expires"} ${date(doc.expiry_date)}` : "No expiry date yet"} · uploaded {dateTime(doc.uploaded_at)}
                    {doc.original_filename && ` · ${doc.original_filename}`}
                  </div>
                  {doc.rejection_reason && <div className="mt-1 text-sm text-bad">Not accepted: {doc.rejection_reason}</div>}
                </div>
                {doc.has_file && <Button variant="ghost" onClick={() => openFile(`/compliance/documents/${doc.id}/file`).catch(setOpenError)}>Open file</Button>}
              </li>
            ))}
          </ul>
        )}
      </Panel>
      {uploading && <UploadDialog supplierId={supplierId} initialType={uploading} onClose={() => setUploading(null)} />}
    </div>
  );
}

function UploadDialog({ supplierId, initialType, onClose }: { supplierId: string; initialType: string; onClose: () => void }) {
  const [docType, setDocType] = useState(initialType);
  const [expiry, setExpiry] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.set("doc_type", docType);
      if (expiry) fd.set("expiry_date", expiry);
      fd.set("file", file!);
      return api(`/suppliers/${supplierId}/documents`, { method: "POST", formData: fd });
    },
    onSuccess: () => {
      ["documents", "compliance", "notifications"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onClose();
    },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Modal title="Upload a compliance document" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Document type">
          <select className={inputCls} value={docType} onChange={(e) => setDocType(e.target.value)}>
            {DOC_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </Field>
        <Field label="File" hint="PDF, PNG or JPG, up to 5 MB.">
          <input className={inputCls} type="file" required accept="application/pdf,image/png,image/jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
        <Field label="Expiry date on the document (optional)" hint="Procurement confirms the dates when they check it.">
          <input className={inputCls} type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} />
        </Field>
        <ErrorNote error={m.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={!file || m.isPending}>{m.isPending ? "Uploading…" : "Upload"}</Button>
        </div>
      </form>
    </Modal>
  );
}

/** Procurement checks an uploaded document against the original and confirms its dates. */
export function ReviewDialog({ supplierId, supplierName, documentId, onClose }: { supplierId: string; supplierName: string; documentId: string; onClose: () => void }) {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["documents", supplierId], queryFn: () => api<SupplierDocuments>(`/suppliers/${supplierId}/documents`) });
  const doc = q.data?.documents.find((d) => d.id === documentId);
  const [issue, setIssue] = useState("");
  const [expiry, setExpiry] = useState("");
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState<"verify" | "reject">("verify");
  const [openError, setOpenError] = useState<unknown>(null);
  const qc = useQueryClient();
  const done = () => { ["documents", "compliance", "scorecards"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); onClose(); };
  const verify = useMutation({ mutationFn: () => api(`/compliance/documents/${documentId}/verify`, { body: { issue_date: issue, expiry_date: expiry || doc?.expiry_date } }), onSuccess: done });
  const reject = useMutation({ mutationFn: () => api(`/compliance/documents/${documentId}/reject`, { body: { reason } }), onSuccess: done });

  return (
    <Modal title={`Check ${supplierName}'s document`} onClose={onClose}>
      {!doc ? <Loading /> : (
        <div className="space-y-4">
          <div className="rounded-md border border-line bg-paper px-3 py-2 text-sm">
            <div className="font-semibold">{docTypeLabel(doc.doc_type)}</div>
            <div className="text-muted">
              Uploaded {dateTime(doc.uploaded_at)}{doc.original_filename && ` · ${doc.original_filename}`}
              {doc.expiry_date && ` · supplier says it expires ${date(doc.expiry_date)}`}
            </div>
            {doc.has_file ? (
              <Button variant="ghost" className="-ml-3 mt-1" onClick={() => openFile(`/compliance/documents/${doc.id}/file`).catch(setOpenError)}>Open the file</Button>
            ) : <p className="mt-1 text-xs text-muted">Demonstration record: there is no file to open.</p>}
          </div>
          <ErrorNote error={openError} />
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-1.5"><input type="radio" checked={mode === "verify"} onChange={() => setMode("verify")} /> It's correct</label>
            <label className="flex items-center gap-1.5"><input type="radio" checked={mode === "reject"} onChange={() => setMode("reject")} /> Send it back</label>
          </div>
          {mode === "verify" ? (
            <form onSubmit={(e) => { e.preventDefault(); verify.mutate(); }} className="space-y-4">
              <p className="text-sm text-muted">Copy the dates from the document itself.</p>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Issue date"><input className={inputCls} type="date" required value={issue} onChange={(e) => setIssue(e.target.value)} /></Field>
                <Field label="Expiry date"><input className={inputCls} type="date" required value={expiry || doc.expiry_date || ""} onChange={(e) => setExpiry(e.target.value)} /></Field>
              </div>
              {user && <p className="text-xs text-muted">Recorded in the audit log as verified by {user.full_name}. You can't verify a document you uploaded yourself.</p>}
              <ErrorNote error={verify.error} />
              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
                <Button type="submit" disabled={verify.isPending}>Mark as verified</Button>
              </div>
            </form>
          ) : (
            <form onSubmit={(e) => { e.preventDefault(); reject.mutate(); }} className="space-y-4">
              <Field label="What's wrong with it?" hint="The supplier sees this, so say what they need to send instead.">
                <textarea className={inputCls} rows={3} required minLength={5} value={reason} onChange={(e) => setReason(e.target.value)} />
              </Field>
              <ErrorNote error={reject.error} />
              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
                <Button type="submit" variant="danger" disabled={reject.isPending}>Send back to supplier</Button>
              </div>
            </form>
          )}
        </div>
      )}
    </Modal>
  );
}
