import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "../components/Layout";
import { ErrorNote, Loading, Panel, Stat } from "../components/ui";
import { KpiBars } from "./Suppliers";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { date } from "../lib/format";
import type { Scorecard } from "../lib/types";

/** Supplier portal: knowing how you're measured helps you improve. */
export function MyScorecard() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["my-scorecard"], queryFn: () => api<Scorecard>(`/suppliers/${user!.supplier_id}/scorecard`), enabled: Boolean(user?.supplier_id) });
  if (q.error) return <ErrorNote error={q.error} />;
  if (!q.data) return <Loading />;
  const c = q.data;
  return (
    <>
      <PageHeader title="My scorecard" intro="How MICS measures your performance. The same scores are used when choosing suppliers for new opportunities." />
      <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
        <Panel>
          <Stat label="Overall grade" value={<span className="text-5xl">{c.grade}</span>} sub={c.overall != null ? `${c.overall.toFixed(0)} out of 100` : "Not enough recent activity to score"} />
        </Panel>
        <Panel title="What makes up the score">
          <KpiBars card={c} />
          <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-2 border-t border-line-soft pt-4 text-sm sm:grid-cols-4">
            <div><dt className="text-muted">Deliveries</dt><dd className="font-semibold">{c.evidence.deliveries}</dd></div>
            <div><dt className="text-muted">Average days late</dt><dd className="font-semibold">{c.evidence.avg_days_late?.toFixed(1) ?? "-"}</dd></div>
            <div><dt className="text-muted">Tax clearance valid until</dt><dd className="font-semibold">{date(c.evidence.tax_clearance_expiry)}</dd></div>
            <div><dt className="text-muted">B-BBEE certificate until</dt><dd className="font-semibold">{date(c.evidence.bbbee_expiry)}</dd></div>
          </dl>
        </Panel>
      </div>
    </>
  );
}
