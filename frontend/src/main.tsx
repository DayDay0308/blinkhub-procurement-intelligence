import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import "./index.css";
import { AuthProvider, useAuth } from "./lib/auth";
import { Dashboard } from "./pages/Dashboard";
import { InvoiceDetail } from "./pages/InvoiceDetail";
import { Invoices } from "./pages/Invoices";
import { Login } from "./pages/Login";
import { MyScorecard } from "./pages/MyScorecard";
import { Notifications } from "./pages/Notifications";
import { PurchaseOrders } from "./pages/PurchaseOrders";
import { FlagDetail, Risk } from "./pages/Risk";
import { SubmitInvoice } from "./pages/SubmitInvoice";
import { Suppliers } from "./pages/Suppliers";

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } });

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-8"><Loading /></div>;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

function Home() {
  const { user } = useAuth();
  return user?.role === "SUPPLIER" ? <Invoices /> : <Dashboard />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<Protected><Layout /></Protected>}>
              <Route index element={<Home />} />
              <Route path="invoices" element={<Invoices />} />
              <Route path="invoices/:id" element={<InvoiceDetail />} />
              <Route path="purchase-orders" element={<PurchaseOrders />} />
              <Route path="risk" element={<Risk />} />
              <Route path="risk/flags/:id" element={<FlagDetail />} />
              <Route path="suppliers" element={<Suppliers />} />
              <Route path="notifications" element={<Notifications />} />
              <Route path="submit" element={<SubmitInvoice />} />
              <Route path="my-scorecard" element={<MyScorecard />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
