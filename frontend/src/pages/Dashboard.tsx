import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useState } from "react";
import { PageHeader } from "../components/Layout";
import { TermsRuler } from "../components/TermsRuler";
import { Loading, Panel, Segmented, Stat, SupplierType } from "../components/ui";
import { api } from "../lib/api";
import { money, moneyShort, pct, PROVINCES } from "../lib/format";
import type { DataSource, Invoice, Overview, Page } from "../lib/types";

const LARGE = "#2a78d6";
const SMME = "#eb6834";
const GRID = "#e8eae4";
const AXIS = { fontSize: 12, fill: "#5b6272" };
const SMME_TARGET = 0.3;

const SOURCES: { value: DataSource; label: string }[] = [
  { value: "CASE_STUDY", label: "Case study" },
  { value: "SYNTHETIC", label: "Synthetic year" },
  { value: "ALL", label: "All" },
];

function tooltipMoney(v: number) {
  return money(v);
}

export function Dashboard() {
  const [src, setSrc] = useState<DataSource>("CASE_STUDY");
  const q = useQuery({ queryKey: ["overview", src], queryFn: () => api<Overview>("/analytics/overview", { params: { data_source: src } }) });
  const overdue = useQuery({
    queryKey: ["invoices", "overdue"],
    queryFn: () => api<Page<Invoice>>("/invoices", { params: { overdue: true } }),
  });

  const d = q.data;
  const note =
    src === "CASE_STUDY"
      ? "The 8 suppliers, 12 purchase orders and 8 invoices from the case study."
      : src === "SYNTHETIC"
        ? "Synthetic demonstration year (about 450 suppliers, R85m). Not MICS's real performance."
        : "Case-study sample plus the synthetic demonstration year.";

  return (
    <>
      <PageHeader
        title="Where the money goes, and what needs attention"
        intro={note}
        action={<Segmented ariaLabel="Data shown" value={src} options={SOURCES} onChange={setSrc} />}
      />
      {!d ? (
        <Loading what="Loading figures" />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
            {[
              <Stat key="s" label="Committed spend" value={moneyShort(d.spend.spend)} sub={`${d.spend.purchase_orders} purchase orders`} />,
              <Stat key="m" label="Spend with SMMEs" value={pct(d.spend.smme_share)} tone={d.spend.smme_share < SMME_TARGET ? "bad" : "good"} sub={`Target ${pct(SMME_TARGET, 0)}`} />,
              <Stat key="b" label="B-BBEE recognised spend" value={pct(d.spend.bbbee_recognition)} sub="Level 1 counts 135%" />,
              <Stat key="o" label="Overdue invoices" value={moneyShort(d.invoices.overdue_value)} tone={d.invoices.overdue_invoices ? "bad" : undefined} sub={`${d.invoices.overdue_invoices} invoices, ${d.invoices.overdue_smme_invoices} from SMMEs`} />,
              <Stat key="p" label="Paid within 30 days" value={pct(d.invoices.pct_paid_within_terms)} sub={d.invoices.avg_days_to_pay_smme != null ? `SMMEs ${d.invoices.avg_days_to_pay_smme.toFixed(0)}d vs large ${d.invoices.avg_days_to_pay_large?.toFixed(0)}d` : undefined} />,
              <Stat key="r" label="Open risk flags" value={d.risk.open_flags} sub={`${d.risk.critical_high} critical or high`} />,
            ].map((s, i) => (
              <div key={i} className="bg-surface p-4">{s}</div>
            ))}
          </div>

          <div className="grid items-start gap-5 lg:grid-cols-[1.3fr_1fr]">
            <Panel title="Spend by category: SMMEs and large enterprises">
              <ResponsiveContainer width="100%" height={Math.max(220, d.by_category.length * 34)}>
                <BarChart data={d.by_category.map((c) => ({ ...c, smme: +c.smme_spend, large: +c.large_spend }))} layout="vertical" margin={{ left: 8, right: 16 }} barGap={2}>
                  <CartesianGrid horizontal={false} stroke={GRID} />
                  <XAxis type="number" tick={AXIS} tickFormatter={moneyShort} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="category" tick={AXIS} width={130} axisLine={false} tickLine={false} />
                  <Tooltip formatter={tooltipMoney} cursor={{ fill: "#f3f4f1" }} />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                  <Bar isAnimationActive={false} dataKey="large" name="Large enterprise" fill={LARGE} radius={[0, 4, 4, 0]} barSize={10} />
                  <Bar isAnimationActive={false} dataKey="smme" name="SMME" fill={SMME} radius={[0, 4, 4, 0]} barSize={10} />
                </BarChart>
              </ResponsiveContainer>
            </Panel>

            <Panel title="Invoices past 30-day terms" action={<Link to="/invoices?view=overdue" className="text-sm font-semibold text-large hover:underline">See all</Link>}>
              {overdue.data?.items.length ? (
                <ul className="divide-y divide-line-soft">
                  {overdue.data.items
                    .filter((i) => (src === "ALL" ? true : src === "CASE_STUDY" ? i.invoice_number.startsWith("INV0") : !i.invoice_number.startsWith("INV0")))
                    .slice(0, 6)
                    .map((i) => (
                      <li key={i.id}>
                        <Link to={`/invoices/${i.id}`} className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 py-2.5 hover:bg-paper/60">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-semibold">{i.invoice_number} · {i.supplier.legal_name}</div>
                            <SupplierType type={i.supplier.supplier_type} />
                          </div>
                          <div className="text-right text-sm font-semibold">{money(i.amount)}</div>
                          <div className="col-span-2"><TermsRuler days={i.days_outstanding} state={i.sla_state} /></div>
                        </Link>
                      </li>
                    ))}
                </ul>
              ) : (
                <p className="text-sm text-muted">No invoices are past terms.</p>
              )}
            </Panel>
          </div>

          <div className="grid items-start gap-5 lg:grid-cols-2">
            <Panel title="Who receives the money">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted">
                  <tr><th className="pb-2 font-medium">Supplier</th><th className="hidden pb-2 font-medium sm:table-cell">B-BBEE</th><th className="pb-2 text-right font-medium">Spend</th><th className="w-[30%] pb-2 pl-3 font-medium">Share</th></tr>
                </thead>
                <tbody className="divide-y divide-line-soft">
                  {d.top_suppliers.slice(0, 8).map((s) => (
                    <tr key={s.supplier_id}>
                      <td className="py-2"><div className="font-medium">{s.supplier}</div><SupplierType type={s.is_smme ? "SMME" : "LARGE"} /></td>
                      <td className="hidden py-2 text-muted sm:table-cell">{s.bbbee_level ? `Level ${s.bbbee_level}` : "Non-compliant"}</td>
                      <td className="py-2 text-right font-medium">{money(s.spend)}</td>
                      <td className="py-2 pl-3">
                        <div className="flex items-center gap-2">
                          <div className="h-2 flex-1 rounded-full bg-line-soft"><div className="h-2 rounded-full" style={{ width: `${s.share * 100}%`, background: s.is_smme ? SMME : LARGE }} /></div>
                          <span className="w-10 text-right text-xs text-muted">{pct(s.share, 0)}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>

            <div className="space-y-5">
              <Panel title="Spend by province">
                <ul className="space-y-2">
                  {d.by_province.map((p) => {
                    const share = +p.spend / +d.spend.spend;
                    return (
                      <li key={p.province} className="grid grid-cols-[120px_1fr_64px] items-center gap-3 text-sm">
                        <span>{PROVINCES[p.province] ?? p.province}</span>
                        <div className="h-2 rounded-full bg-line-soft"><div className="h-2 rounded-full bg-ink" style={{ width: `${share * 100}%` }} /></div>
                        <span className="text-right text-muted">{pct(share, 0)}</span>
                      </li>
                    );
                  })}
                </ul>
              </Panel>
              {d.monthly.length > 2 && (
                <Panel title="Monthly spend">
                  <ResponsiveContainer width="100%" height={180}>
                    <LineChart data={d.monthly.map((m) => ({ ...m, spend: +m.spend, smme: +m.smme_spend }))} margin={{ right: 12 }}>
                      <CartesianGrid vertical={false} stroke={GRID} />
                      <XAxis dataKey="month" tick={AXIS} tickLine={false} axisLine={false} />
                      <YAxis tick={AXIS} tickFormatter={moneyShort} tickLine={false} axisLine={false} width={56} />
                      <Tooltip formatter={tooltipMoney} />
                      <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                      <Line isAnimationActive={false} dataKey="spend" name="All suppliers" stroke={LARGE} strokeWidth={2} dot={false} />
                      <Line isAnimationActive={false} dataKey="smme" name="SMMEs" stroke={SMME} strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </Panel>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
