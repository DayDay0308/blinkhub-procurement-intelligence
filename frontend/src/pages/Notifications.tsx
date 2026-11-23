import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/Layout";
import { Button, Empty, Loading, Panel } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime } from "../lib/format";
import type { Notification, Page } from "../lib/types";

export function Notifications() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["notifications", "all"], queryFn: () => api<Page<Notification>>("/notifications") });
  const read = useMutation({
    mutationFn: (id: string) => api(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const link = (n: Notification) =>
    n.entity_type === "INVOICE" ? `/invoices/${n.entity_id}`
    : n.entity_type === "RISK_FLAG" ? `/risk/flags/${n.entity_id}`
    : n.kind.startsWith("DOC_") ? (user?.role === "SUPPLIER" ? "/my-documents" : "/compliance")
    : null;

  return (
    <>
      <PageHeader title="Notifications" intro="Payment-terms reminders, escalations and document reminders. Each one is sent once." />
      <Panel>
        {q.isLoading ? <Loading /> : !q.data?.items.length ? <Empty title="You're all caught up">Reminders appear here when an invoice reaches day 20 or 25 of its terms.</Empty> : (
          <ul className="-my-4 divide-y divide-line-soft">
            {q.data.items.map((n) => {
              const to = link(n);
              return (
                <li key={n.id} className="flex items-start gap-3 py-3">
                  <span className={clsx("mt-2 size-2 shrink-0 rounded-full", n.read_at ? "bg-transparent" : "bg-smme")} aria-label={n.read_at ? undefined : "Unread"} />
                  <div className="min-w-0 flex-1">
                    <div className={clsx("text-sm", !n.read_at && "font-semibold")}>{to ? <Link to={to} className="hover:underline" onClick={() => !n.read_at && read.mutate(n.id)}>{n.title}</Link> : n.title}</div>
                    {n.body && <p className="text-sm text-muted">{n.body}</p>}
                    <div className="mt-0.5 text-xs text-muted">{dateTime(n.created_at)}</div>
                  </div>
                  {!n.read_at && <Button variant="ghost" onClick={() => read.mutate(n.id)}>Mark read</Button>}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </>
  );
}
