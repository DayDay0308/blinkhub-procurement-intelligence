import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUp, Download, Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { PageHeader } from "../components/Layout";
import { Badge, Button, Empty, ErrorNote, Loading, Panel } from "../components/ui";
import { api } from "../lib/api";
import { date, label, money, PROVINCES } from "../lib/format";
import type { AskAnswer } from "../lib/types";

const MONEY = /amount|spend|value|total|paid_last/i;
const PCT = /_pct$|share/i;
const DATE = /date$|expiry$/i;

function cell(column: string, v: AskAnswer["rows"][number][number]) {
  if (v === null || v === undefined) return <span className="text-muted">-</span>;
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number" && MONEY.test(column)) return money(v);
  if (typeof v === "number" && PCT.test(column)) return `${v}%`;
  if (typeof v === "string" && DATE.test(column) && /^\d{4}-\d{2}-\d{2}$/.test(v)) return date(v);
  if (column === "province" && typeof v === "string") return PROVINCES[v] ?? v;
  if (typeof v === "string" && /^[A-Z_]{3,}$/.test(v) && v !== "SMME") return label(v);
  return String(v);
}

function toCsv(a: AskAnswer) {
  const esc = (v: unknown) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replaceAll('"', '""')}"` : String(v));
  return [a.columns, ...a.rows].map((r) => r.map(esc).join(",")).join("\n");
}

export function Ask() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<AskAnswer[]>([]);
  const meta = useQuery({ queryKey: ["ask", "suggestions"], queryFn: () => api<{ ai_enabled: boolean; suggestions: { id: string; question: string }[] }>("/ask/suggestions") });
  const m = useMutation({
    mutationFn: (q: string) => api<AskAnswer>("/ask", { body: { question: q } }),
    onSuccess: (a) => { setHistory((h) => [a, ...h].slice(0, 10)); setQuestion(""); },
  });
  const submit = (e?: FormEvent, q = question) => { e?.preventDefault(); if (q.trim().length >= 3) m.mutate(q.trim()); };
  const latest = history[0];

  return (
    <>
      <PageHeader
        title="Ask BlinkHub"
        intro={meta.data?.ai_enabled
          ? "Ask a question about suppliers, orders, invoices, risk flags or compliance in plain English. The answer comes from a read-only copy of the data, and the query is shown so you can check it."
          : "Pick a question below. With an AI model configured (ANTHROPIC_API_KEY) you can ask anything about suppliers, orders, invoices, risk flags and compliance."}
      />

      <form onSubmit={submit} className="mb-4 flex gap-2 rounded-lg border border-line bg-surface p-2 focus-within:border-large">
        <Sparkles className="mt-2.5 ml-2 size-4 shrink-0 text-muted" aria-hidden />
        <input
          className="min-w-0 flex-1 bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-muted/70"
          placeholder="e.g. Which SMMEs in Limpopo have been waiting longest to be paid?"
          aria-label="Your question"
          value={question}
          maxLength={500}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button type="submit" disabled={m.isPending || question.trim().length < 3} aria-label="Ask"><ArrowUp className="size-4" /> Ask</Button>
      </form>

      <div className="mb-6 flex flex-wrap gap-2">
        {meta.data?.suggestions.map((s) => (
          <button key={s.id} onClick={() => submit(undefined, s.question)} disabled={m.isPending} className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm hover:border-ink disabled:opacity-50">
            {s.question}
          </button>
        ))}
      </div>

      {m.isPending && <Loading what="Working out the answer" />}
      <ErrorNote error={m.error} />
      {!m.isPending && latest && <AnswerPanel a={latest} />}
      {!latest && !m.isPending && !m.error && <Empty title="Ask your first question">Answers appear here as a table you can download.</Empty>}

      {history.length > 1 && (
        <div className="mt-6">
          <h2 className="mb-2 text-sm font-semibold text-muted">Earlier this session</h2>
          <ul className="space-y-1 text-sm">
            {history.slice(1).map((h, i) => (
              <li key={i}><button className="text-left text-large hover:underline" onClick={() => setHistory((all) => [h, ...all.filter((x) => x !== h)])}>{h.question}</button></li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function AnswerPanel({ a }: { a: AskAnswer }) {
  const [showSql, setShowSql] = useState(false);
  if (!a.answered) {
    return (
      <Panel title="I can't answer that one">
        <p className="text-sm">{a.explanation}</p>
      </Panel>
    );
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([toCsv(a)], { type: "text/csv" }));
    Object.assign(document.createElement("a"), { href: url, download: "blinkhub-answer.csv" }).click();
    URL.revokeObjectURL(url);
  };
  return (
    <Panel
      title={a.title}
      action={
        <div className="flex items-center gap-2">
          <Badge tone="ink">{a.method === "AI" ? "Written by the AI model" : "Saved question"}</Badge>
          <Button variant="ghost" onClick={download} disabled={!a.rows.length}><Download className="size-4" aria-hidden /> CSV</Button>
        </div>
      }
    >
      <p className="-mt-1 mb-3 text-sm text-muted">
        {a.explanation} {a.rows.length} {a.rows.length === 1 ? "row" : "rows"}{a.truncated ? " (first 200 shown)" : ""}.
      </p>
      {a.rows.length === 0 ? <p className="text-sm">No rows match.</p> : (
        <div className="-mx-4 max-h-[55vh] overflow-auto border-y border-line-soft">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface text-left text-xs text-muted">
              <tr>{a.columns.map((c) => <th key={c} className="whitespace-nowrap border-b border-line-soft px-4 py-2 font-medium">{label(c)}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {a.rows.map((r, i) => (
                <tr key={i}>
                  {r.map((v, j) => (
                    <td key={j} className={`px-4 py-2 ${typeof v === "number" ? "text-right" : ""} ${j === 0 ? "font-medium" : ""}`}>{cell(a.columns[j], v)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <button className="mt-3 text-sm font-semibold text-large hover:underline" onClick={() => setShowSql((s) => !s)}>
        {showSql ? "Hide the query" : "Show the query"}
      </button>
      {showSql && <pre className="mt-2 overflow-x-auto rounded-md bg-ink p-3 text-xs leading-relaxed text-white"><code>{a.sql}</code></pre>}
    </Panel>
  );
}
