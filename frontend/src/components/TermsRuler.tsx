import clsx from "clsx";
import type { SlaState } from "../lib/types";

/**
 * The 30-day payment-terms ruler (case study Problem 4).
 *
 * A track from day 0 to day 60 with the escalation ladder marked: warning at day 20,
 * escalation at day 25, breach after day 30. The marker shows where this invoice sits:
 * days outstanding if unpaid, or the days it took to pay. Anything past 60 days is pinned
 * to the end and labelled.
 */
const MAX = 60;
const STATE_TEXT: Record<SlaState, string> = {
  PAID: "Paid",
  ON_TRACK: "On track",
  WARNING: "Due soon",
  ESCALATED: "Escalated",
  BREACHED: "Past terms",
};

export function TermsRuler({ days, state, size = "sm" }: { days: number; state: SlaState; size?: "sm" | "lg" }) {
  const pos = Math.min(days, MAX) / MAX;
  const late = state === "BREACHED";
  const lg = size === "lg";
  const summary = state === "PAID" ? `Paid in ${days} days` : `${days} days outstanding: ${STATE_TEXT[state].toLowerCase()}`;

  return (
    <div className={clsx("w-full", lg ? "max-w-xl" : "min-w-36")} role="img" aria-label={summary} title={summary}>
      <div className={clsx("relative rounded-full bg-line-soft", lg ? "h-3" : "h-1.5")}>
        {/* escalation ladder: 20-25 warning, 25-30 escalated, 30+ past terms */}
        <div className="absolute inset-y-0 rounded-r-none bg-warn/20" style={{ left: `${(20 / MAX) * 100}%`, width: `${(10 / MAX) * 100}%` }} />
        <div className="absolute inset-y-0 rounded-r-full bg-bad/15" style={{ left: `${(30 / MAX) * 100}%`, right: 0 }} />
        <div className="absolute inset-y-[-3px] w-px bg-ink/40" style={{ left: `${(30 / MAX) * 100}%` }} aria-hidden />
        <div
          className={clsx(
            "absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface",
            lg ? "size-5" : "size-3",
            state === "PAID" ? "bg-good" : late ? "bg-bad" : state === "ON_TRACK" ? "bg-ink" : "bg-warn",
          )}
          style={{ left: `${pos * 100}%` }}
        />
      </div>
      <div className={clsx("mt-1 flex justify-between text-muted", lg ? "text-xs" : "text-[11px]")}>
        <span className={clsx("font-semibold", late ? "text-bad" : state === "PAID" ? "text-good" : "text-ink")}>
          {state === "PAID" ? `Paid in ${days}d` : `${days}d${days > MAX ? " (60+)" : ""}`}
        </span>
        {!lg && <span>30-day terms</span>}
      </div>
      {lg && (
        <div className="relative mt-1 h-4 text-xs text-muted" aria-hidden>
          {[[20, "Day 20"], [30, "Day 30 due"], [60, "60+"]].map(([d, t]) => (
            <span key={d} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${(+d / MAX) * 100}%`, ...(d === 60 ? { transform: "translateX(-100%)" } : {}) }}>{t}</span>
          ))}
        </div>
      )}
    </div>
  );
}
