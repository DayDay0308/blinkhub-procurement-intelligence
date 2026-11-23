import clsx from "clsx";
import { Loader2, X } from "lucide-react";
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from "react";
import { ApiError } from "../lib/api";
import { label } from "../lib/format";

export function Button({ variant = "primary", className, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  return (
    <button
      {...p}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-md px-3.5 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-ink text-white hover:bg-ink-soft",
        variant === "secondary" && "border border-line bg-surface text-ink hover:bg-paper",
        variant === "danger" && "border border-bad/40 bg-surface text-bad hover:bg-bad/5",
        variant === "ghost" && "text-muted hover:bg-paper hover:text-ink",
        className,
      )}
    />
  );
}

/** A bordered section with an optional heading row. Panels differ by content, not decoration. */
export function Panel({ title, action, children, className }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx("rounded-lg border border-line bg-surface", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line-soft px-4 py-3">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

const TONE: Record<string, string> = {
  good: "bg-good/10 text-good",
  warn: "bg-warn/10 text-warn",
  bad: "bg-bad/10 text-bad",
  neutral: "bg-paper text-muted",
  ink: "bg-ink/8 text-ink",
};

export function Badge({ tone = "neutral", children }: { tone?: keyof typeof TONE; children: ReactNode }) {
  return <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-semibold", TONE[tone])}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "PAID" || status === "APPROVED" || status === "CONFIRMED" ? (status === "CONFIRMED" ? "bad" : "good")
    : status === "EXCEPTION" || status === "REJECTED" || status === "ESCALATED" ? "bad"
    : status === "PENDING_APPROVAL" || status === "UNDER_REVIEW" ? "warn"
    : "neutral";
  return <Badge tone={tone}>{label(status)}</Badge>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  const tone = severity === "CRITICAL" || severity === "HIGH" ? "bad" : severity === "MEDIUM" ? "warn" : "neutral";
  return <Badge tone={tone}>{label(severity)}</Badge>;
}

/** Supplier type is a series identity (same colours as the Power BI report), shown as a dot + text. */
export function SupplierType({ type }: { type: string }) {
  const smme = type === "SMME";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted">
      <span className={clsx("size-2 rounded-full", smme ? "bg-smme" : "bg-large")} aria-hidden />
      {smme ? "SMME" : "Large enterprise"}
    </span>
  );
}

export function Stat({ label: l, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "bad" | "good" }) {
  return (
    <div className="min-w-0">
      <div className="text-sm text-muted">{l}</div>
      <div className={clsx("mt-1 text-2xl font-semibold tracking-tight", tone === "bad" && "text-bad", tone === "good" && "text-good")}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export function Field({ label: l, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium">{l}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const searchCls =
  "rounded-md border border-line bg-surface px-3 py-2 text-sm placeholder:text-muted/70 focus:border-large focus:outline-none";

export const inputCls =
  "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm placeholder:text-muted/70 focus:border-large focus:outline-none";

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-muted">
      <Loader2 className="size-4 animate-spin" /> {what}…
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as ApiError;
  const details = Array.isArray(e.details) ? (e.details as { field: string; message: string }[]) : null;
  return (
    <div role="alert" className="rounded-md border border-bad/30 bg-bad/5 px-3 py-2 text-sm text-bad">
      {e.message ?? String(error)}
      {details && (
        <ul className="mt-1 list-disc pl-4">
          {details.map((d) => <li key={d.field}>{d.field}: {d.message}</li>)}
        </ul>
      )}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="py-10 text-center">
      <p className="font-semibold">{title}</p>
      {children && <p className="mt-1 text-sm text-muted">{children}</p>}
    </div>
  );
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-ink/40 p-4 pt-[8vh]" onClick={onClose}>
      <div role="dialog" aria-modal aria-label={title} className={clsx("max-h-[85vh] w-full overflow-y-auto rounded-lg bg-surface shadow-xl", wide ? "max-w-3xl" : "max-w-lg")} onClick={(e) => e.stopPropagation()}>
        <header className="flex items-center justify-between border-b border-line-soft px-5 py-3">
          <h2 className="font-semibold">{title}</h2>
          <button aria-label="Close" onClick={onClose} className="rounded p-1 text-muted hover:bg-paper"><X className="size-4" /></button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, ariaLabel }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; ariaLabel: string }) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="inline-flex rounded-md border border-line bg-surface p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={clsx("rounded px-3 py-1.5 text-sm font-medium", value === o.value ? "bg-ink text-white" : "text-muted hover:text-ink")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
