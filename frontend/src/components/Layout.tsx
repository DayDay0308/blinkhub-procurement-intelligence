import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Bell, FileCheck2, Sparkles, FileText, Gauge, LogOut, PackageCheck, PlusCircle, ShieldAlert, Star, Users } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ROLE_LABEL } from "../lib/format";
import type { Notification, Page, Role } from "../lib/types";

interface NavItem {
  to: string;
  label: string;
  icon: typeof Gauge;
  roles?: Role[];
}

const STAFF: Role[] = ["ADMIN", "PROCUREMENT_OFFICER", "FINANCE_OFFICER", "APPROVER", "MANAGER", "AUDITOR"];

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: Gauge, roles: STAFF },
  { to: "/ask", label: "Ask BlinkHub", icon: Sparkles, roles: STAFF },
  { to: "/invoices", label: "Invoices", icon: FileText, roles: STAFF },
  { to: "/purchase-orders", label: "Purchase orders", icon: PackageCheck, roles: ["ADMIN", "PROCUREMENT_OFFICER", "FINANCE_OFFICER", "MANAGER", "AUDITOR"] },
  { to: "/risk", label: "Risk monitoring", icon: ShieldAlert, roles: ["ADMIN", "PROCUREMENT_OFFICER", "FINANCE_OFFICER", "MANAGER", "AUDITOR"] },
  { to: "/suppliers", label: "Supplier performance", icon: Users, roles: STAFF },
  { to: "/compliance", label: "Supplier compliance", icon: FileCheck2, roles: STAFF },
  // supplier portal
  { to: "/", label: "My invoices", icon: FileText, roles: ["SUPPLIER"] },
  { to: "/submit", label: "Submit an invoice", icon: PlusCircle, roles: ["SUPPLIER"] },
  { to: "/my-documents", label: "My documents", icon: FileCheck2, roles: ["SUPPLIER"] },
  { to: "/my-scorecard", label: "My scorecard", icon: Star, roles: ["SUPPLIER"] },
];

export function Layout() {
  const { user, signOut } = useAuth();
  const unread = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => api<Page<Notification>>("/notifications", { params: { unread_only: true } }),
    refetchInterval: 60_000,
  });
  if (!user) return null;
  const items = NAV.filter((n) => !n.roles || n.roles.includes(user.role));
  const unreadCount = unread.data?.total ?? 0;

  return (
    <div className="min-h-screen md:grid md:grid-cols-[232px_1fr]">
      <div className="bg-ink text-white">
      <aside className="md:sticky md:top-0 md:h-screen md:overflow-y-auto">
        <div className="px-5 pb-5 pt-6">
          <div className="text-lg font-bold leading-tight">Blink</div>
          <div className="text-sm text-white/70">{user.role === "SUPPLIER" ? "Supplier portal" : "Procurement intelligence"}</div>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible">
          {items.map((n) => (
            <NavLink
              key={n.to + n.label}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                clsx("flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm", isActive ? "bg-white/12 font-semibold" : "text-white/75 hover:bg-white/8 hover:text-white")
              }
            >
              <n.icon className="size-4" aria-hidden />
              {n.label}
            </NavLink>
          ))}
          <NavLink
            to="/notifications"
            className={({ isActive }) =>
              clsx("flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm", isActive ? "bg-white/12 font-semibold" : "text-white/75 hover:bg-white/8 hover:text-white")
            }
          >
            <Bell className="size-4" aria-hidden />
            Notifications
            {unreadCount > 0 && <span className="ml-auto rounded-full bg-smme px-1.5 text-xs font-bold text-white">{unreadCount}</span>}
          </NavLink>
        </nav>
        <div className="hidden px-5 pt-6 text-xs leading-relaxed text-white/55 md:block">
          Candidate prototype for the BlinkHub Procurement Innovation Challenge. All data is fictional or synthetic.
        </div>
      </aside>
      </div>

      <div className="min-w-0">
        <header className="flex items-center justify-end gap-4 border-b border-line bg-surface px-6 py-3">
          <div className="text-right text-sm">
            <div className="font-semibold">{user.full_name}</div>
            <div className="text-xs text-muted">{ROLE_LABEL[user.role]}</div>
          </div>
          <button onClick={signOut} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted hover:bg-paper hover:text-ink">
            <LogOut className="size-4" aria-hidden /> Sign out
          </button>
        </header>
        <main className="mx-auto max-w-[1280px] px-4 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function PageHeader({ title, intro, action }: { title: string; intro?: string; action?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {intro && <p className="mt-1 text-[15px] text-muted">{intro}</p>}
      </div>
      {action}
    </div>
  );
}
