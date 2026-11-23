import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PageHeader } from "../components/Layout";
import { Button, Empty, ErrorNote, Field, inputCls, Loading, Panel, Segmented, SeverityBadge, Stat, StatusBadge, SupplierType } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { date, dateTime, label, money, moneyShort, pct, ROLE_LABEL } from "../lib/format";
import type { Flag, Page } from "../lib/types";

interface Summary {
  open_flags: number;
  value_under_review: string;
  by_rule_and_severity: { rule_code: string; name: string; severity: string; flags: number; invoice_value: string }[];
  by_status: Record<string, number>;
}
interface Evaluation {
  note: string;
  rules: { code: string; name: string; planted: number; caught: number; flags: number; precision: number | null; precision_any: number | null; recall: number | null }[];
  overall: { precision: number | null; precision_any: number | null; recall: number | null };
}

type Tab = "queue" | "evaluation";

export function Risk() {
  const [tab, setTab] = useState<Tab>("queue");
  const [rule, setRule] = useState("");
  const [mine, setMine] = useState(false);
  const summary = useQuery({ queryKey: ["risk", "summary"], queryFn: () => api<Summary>("/risk/summary") });
  const flags = useQuery({
    queryKey: ["risk", "flags", rule, mine],
    queryFn: () => api<Page<Flag>>("/risk/flags", { params: { rule_code: rule || undefined, assigned_to_me: mine || undefined, limit: 100 } }),
  });

  const byRule = Object.values(
    (summary.data?.by_rule_and_severity ?? []).reduce<Record<string, { code: string; name: string; flags: number }>>((acc, r) => {
      acc[r.rule_code] ??= { code: r.rule_code, name: r.name, flags: 0 };
      acc[r.rule_code].flags += r.flags;
      return acc;
    }, {}),
  ).sort((a, b) => b.flags - a.flags);
  const critHigh = (summary.data?.by_rule_and_severity ?? []).filter((r) => r.severity === "CRITICAL" || r.severity === "HIGH").reduce((s, r) => s + r.flags, 0);

  return (
    <>
      <PageHeader
        title="Risk monitoring"
        intro="Patterns worth a second look, each with the evidence behind it. A flag is a reason to investigate, not an accusation; only a person can confirm or dismiss one."
        action={<Segmented ariaLabel="Risk view" value={tab} onChange={setTab} options={[{ value: "queue", label: "Investigation queue" }, { value: "evaluation", label: "How accurate is it?" }]} />}
      />
      {tab === "evaluation" ? <EvaluationView /> : (
        <div className="space-y-5">
          {summary.data && (
            <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
              <div className="bg-surface p-4"><Stat label="Open flags" value={summary.data.open_flags} /></div>
              <div className="bg-surface p-4"><Stat label="Critical or high" value={critHigh} tone={critHigh ? "bad" : undefined} /></div>
              <div className="bg-surface p-4"><Stat label="Invoice value under review" value={moneyShort(summary.data.value_under_review)} /></div>
              <div className="bg-surface p-4"><Stat label="Confirmed / dismissed" value={`${summary.data.by_status.CONFIRMED ?? 0} / ${summary.data.by_status.DISMISSED ?? 0}`} /></div>
            </div>
          )}
          <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
            <Panel title="By pattern">
              <ul className="-mx-2 space-y-0.5 text-sm">
                <li><button onClick={() => setRule("")} className={`flex w-full justify-between rounded px-2 py-1.5 ${!rule ? "bg-paper font-semibold" : "hover:bg-paper"}`}><span>All patterns</span><span>{summary.data?.open_flags}</span></button></li>
                {byRule.map((r) => (
                  <li key={r.code}>
                    <button onClick={() => setRule(r.code)} className={`flex w-full justify-between gap-2 rounded px-2 py-1.5 text-left ${rule === r.code ? "bg-paper font-semibold" : "hover:bg-paper"}`}>
                      <span>{r.name}</span><span className="text-muted">{r.flags}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <label className="mt-4 flex items-center gap-2 border-t border-line-soft pt-3 text-sm">
                <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Only assigned to me
              </label>
            </Panel>
            <Panel title={`Flags${flags.data ? ` (${flags.data.total})` : ""}`}>
              {flags.isLoading ? <Loading /> : !flags.data?.items.length ? <Empty title="No open flags here" /> : (
                <ul className="-my-4 divide-y divide-line-soft">
                  {flags.data.items.map((f) => (
                    <li key={f.id}>
                      <Link to={`/risk/flags/${f.id}`} className="-mx-4 grid grid-cols-[48px_1fr_auto] items-start gap-4 px-4 py-3 hover:bg-paper/60">
                        <div className="text-center"><div className="text-lg font-bold">{Math.round(f.score)}</div><div className="text-[10px] text-muted">score</div></div>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{f.rule_name}</span><SeverityBadge severity={f.severity} /></div>
                          <p className="mt-0.5 line-clamp-2 text-sm text-muted">{f.explanation.reason}</p>
                          {f.supplier && <div className="mt-1 text-xs">{f.supplier.legal_name} · <SupplierType type={f.supplier.supplier_type} /></div>}
                        </div>
                        <div className="text-right"><StatusBadge status={f.status} /><div className="mt-1 text-xs text-muted">{date(f.detected_at)}</div></div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}

function EvaluationView() {
  const q = useQuery({ queryKey: ["risk", "evaluation"], queryFn: () => api<Evaluation>("/risk/evaluation") });
  if (!q.data) return <Loading what="Scoring the engine against the answer key" />;
  const e = q.data;
  return (
    <div className="space-y-5">
      <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3">
        <div className="bg-surface p-4"><Stat label="Recall: planted problems found" value={pct(e.overall.recall)} /></div>
        <div className="bg-surface p-4"><Stat label="Precision: flags that were real" value={pct(e.overall.precision_any)} sub={`${pct(e.overall.precision)} matched to the exact pattern`} /></div>
        <div className="bg-surface p-4"><Stat label="Measured on" value="Synthetic year" sub="124 problems planted on purpose" /></div>
      </div>
      <Panel title="Per pattern">
        <p className="-mt-1 mb-3 text-sm text-muted">{e.note}</p>
        <div className="-mx-4 overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="border-y border-line-soft text-left text-xs text-muted">
              <tr><th className="px-4 py-2 font-medium">Pattern</th><th className="px-4 py-2 text-right font-medium">Planted</th><th className="px-4 py-2 text-right font-medium">Found</th><th className="px-4 py-2 text-right font-medium">Flags raised</th><th className="px-4 py-2 text-right font-medium">Recall</th><th className="px-4 py-2 text-right font-medium">Precision</th></tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {e.rules.filter((r) => r.planted || r.flags).map((r) => (
                <tr key={r.code}>
                  <td className="px-4 py-2.5 font-medium">{r.name}</td>
                  <td className="px-4 py-2.5 text-right">{r.planted}</td>
                  <td className="px-4 py-2.5 text-right">{r.caught}</td>
                  <td className="px-4 py-2.5 text-right">{r.flags}</td>
                  <td className="px-4 py-2.5 text-right font-semibold">{pct(r.recall, 0)}</td>
                  <td className="px-4 py-2.5 text-right font-semibold">{pct(r.precision_any, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

const NEXT: { status: Flag["status"]; label: string; final?: boolean }[] = [
  { status: "UNDER_REVIEW", label: "Start review" },
  { status: "ESCALATED", label: "Escalate" },
  { status: "DISMISSED", label: "Dismiss", final: true },
  { status: "CONFIRMED", label: "Confirm finding", final: true },
];

export function FlagDetail() {
  const { id } = useParams();
  const { user, can } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["flag", id], queryFn: () => api<Flag>(`/risk/flags/${id}`) });
  const [note, setNote] = useState("");
  const refresh = () => { qc.invalidateQueries({ queryKey: ["flag", id] }); qc.invalidateQueries({ queryKey: ["risk"] }); setNote(""); };
  const setStatus = useMutation({ mutationFn: (status: string) => api(`/risk/flags/${id}/status`, { body: { status, note: note || null } }), onSuccess: refresh });
  const addNote = useMutation({ mutationFn: () => api(`/risk/flags/${id}/notes`, { body: { note } }), onSuccess: refresh });
  const assign = useMutation({ mutationFn: () => api(`/risk/flags/${id}/assign`, { body: { user_id: user!.id } }), onSuccess: refresh });

  if (!q.data) return q.error ? <ErrorNote error={q.error} /> : <Loading />;
  const f = q.data;
  const { reason, ...evidence } = f.explanation;
  const investigator = can("MANAGER", "AUDITOR");
  const closed = f.status === "DISMISSED" || f.status === "CONFIRMED";

  return (
    <>
      <Link to="/risk" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" /> Risk monitoring</Link>
      <div className="mb-6">
        <div className="flex flex-wrap items-center gap-3"><h1 className="text-2xl font-bold tracking-tight">{f.rule_name}</h1><SeverityBadge severity={f.severity} /><StatusBadge status={f.status} /></div>
        <p className="mt-2 max-w-3xl text-[15px]">{reason}</p>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <div className="space-y-5">
          <Panel title="Evidence">
            <dl className="grid grid-cols-[minmax(140px,auto)_1fr] gap-x-6 gap-y-2.5 text-sm">
              <dt className="text-muted">Risk score</dt><dd className="font-semibold">{Math.round(f.score)} / 100</dd>
              {f.supplier && <><dt className="text-muted">Supplier</dt><dd>{f.supplier.legal_name} · <SupplierType type={f.supplier.supplier_type} /></dd></>}
              {Object.entries(evidence).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted">{label(k)}</dt>
                  <dd className="break-words">{renderValue(k, v)}</dd>
                </div>
              ))}
              <dt className="text-muted">First detected</dt><dd>{dateTime(f.detected_at)}</dd>
            </dl>
          </Panel>
          <Panel title="Case notes">
            {f.notes?.length ? (
              <ul className="space-y-3">
                {f.notes.map((n) => (
                  <li key={n.id} className="border-l-2 border-line pl-3">
                    <div className="text-xs text-muted">{n.author} · {ROLE_LABEL[n.role]} · {dateTime(n.created_at)}</div>
                    <p className="mt-0.5 text-sm">{n.note}</p>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No notes yet.</p>}
          </Panel>
        </div>
        <Panel title="Decide">
          <div className="space-y-4">
            <p className="text-sm text-muted">Assigned to: {f.assigned_to ? (f.assigned_to === user?.id ? "you" : "another investigator") : "nobody yet"}</p>
            {investigator && !f.assigned_to && !closed && <Button variant="secondary" onClick={() => assign.mutate()}>Assign to me</Button>}
            <Field label="Note" hint="Required to confirm or dismiss (at least 10 characters). Recorded in the audit log.">
              <textarea className={inputCls} rows={4} value={note} onChange={(e) => setNote(e.target.value)} />
            </Field>
            <ErrorNote error={setStatus.error ?? addNote.error ?? assign.error} />
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" disabled={note.trim().length < 10 || addNote.isPending} onClick={() => addNote.mutate()}>Add note</Button>
              {investigator && NEXT.filter((n) => n.status !== f.status && (!closed || n.status === "UNDER_REVIEW")).map((n) => (
                <Button key={n.status} variant={n.status === "CONFIRMED" ? "danger" : n.final ? "secondary" : "primary"} disabled={setStatus.isPending || (n.final && note.trim().length < 10)} onClick={() => setStatus.mutate(n.status)}>
                  {closed ? "Reopen" : n.label}
                </Button>
              ))}
            </div>
            {!investigator && <p className="text-xs text-muted">Only auditors and managers can change a flag's status.</p>}
          </div>
        </Panel>
      </div>
    </>
  );
}

function renderValue(key: string, v: unknown): React.ReactNode {
  if (v == null) return "-";
  if (Array.isArray(v)) return v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ");
  if (typeof v === "object") return <code className="text-xs">{JSON.stringify(v)}</code>;
  if (typeof v === "number" && /amount|value|total|spend/i.test(key)) return money(v);
  if (typeof v === "number" && /share|pct|ratio/i.test(key) && v <= 1) return pct(v);
  if (typeof v === "string" && /^\d+(\.\d+)?$/.test(v) && /amount|value|total|spend/i.test(key)) return money(v);
  return String(v);
}
