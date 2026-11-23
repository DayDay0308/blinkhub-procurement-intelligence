export type Role = "ADMIN" | "PROCUREMENT_OFFICER" | "FINANCE_OFFICER" | "APPROVER" | "MANAGER" | "AUDITOR" | "SUPPLIER";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  department_id: string | null;
  supplier_id: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
}

export type SlaState = "PAID" | "ON_TRACK" | "WARNING" | "ESCALATED" | "BREACHED";

export interface Invoice {
  id: string;
  invoice_number: string;
  supplier: { id: string; legal_name: string; supplier_type: "SMME" | "LARGE_ENTERPRISE" };
  po_number: string | null;
  amount: string;
  status: string;
  invoice_date: string;
  received_at: string;
  due_date: string;
  paid_at: string | null;
  days_outstanding: number;
  ageing_bucket: string;
  sla_state: SlaState;
  exceptions: string[];
  current_owner: { id: string; full_name: string; role: Role } | null;
}

export interface TimelineEvent {
  at: string;
  action: string;
  by_role: Role | null;
  status: string | null;
  note: string | null;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  supplier: Invoice["supplier"];
  department: string;
  category: string;
  total_amount: string;
  status: string;
  received_amount: string;
  invoiced_amount: string;
}

export interface Flag {
  id: string;
  rule_code: string;
  rule_name: string;
  entity_type: string;
  entity_id: string;
  supplier: { id: string; legal_name: string; supplier_type: string } | null;
  score: number;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  status: "OPEN" | "UNDER_REVIEW" | "ESCALATED" | "DISMISSED" | "CONFIRMED";
  explanation: Record<string, unknown> & { reason: string };
  assigned_to: string | null;
  detected_at: string;
  notes?: { id: string; author: string; role: Role; note: string; created_at: string }[];
}

export interface Scorecard {
  supplier: { id: string; supplier_code: string; legal_name: string; supplier_type: string; province: string; bbbee_level: number | null };
  overall: number | null;
  grade: string;
  status: "SCORED" | "INSUFFICIENT_DATA";
  kpis: Record<"delivery_reliability" | "invoice_accuracy" | "compliance" | "risk_record" | "price_competitiveness", number | null>;
  evidence: { deliveries: number; avg_days_late: number | null; invoices: number; open_flags: number; tax_clearance_expiry: string | null; bbbee_expiry: string | null; price_vs_market_pct: number | null };
}

export interface Notification {
  id: string;
  kind: string;
  entity_type: string;
  entity_id: string;
  title: string;
  body: string | null;
  created_at: string;
  read_at: string | null;
}

export type DataSource = "CASE_STUDY" | "SYNTHETIC" | "ALL";

export interface Overview {
  data_source: DataSource;
  spend: { spend: string; smme_spend: string; smme_share: number; bbbee_recognition: number; purchase_orders: number; suppliers_paid: number };
  invoices: {
    open_invoices: number;
    overdue_invoices: number;
    overdue_value: string;
    overdue_smme_invoices: number;
    pct_paid_within_terms: number | null;
    avg_days_to_pay_smme: number | null;
    avg_days_to_pay_large: number | null;
    pct_without_po: number | null;
    open_without_owner: number;
  };
  ageing: { bucket: string; invoices: number; value: string }[];
  by_category: { category: string; spend: string; smme_spend: string; large_spend: string }[];
  by_department: { department: string; spend: string }[];
  by_province: { province: string; spend: string; smme_spend: string }[];
  monthly: { month: string; spend: string; smme_spend: string }[];
  top_suppliers: { supplier_id: string; supplier: string; is_smme: boolean; bbbee_level: number | null; spend: string; share: number }[];
  risk: { open_flags: number; critical_high: number; value_under_review: string };
}

export type ComplianceState = "EXPIRED" | "MISSING" | "PENDING_VERIFICATION" | "EXPIRING" | "VALID";

export interface Requirement {
  requirement: "TAX_CLEARANCE" | "BBBEE";
  label: string;
  state: ComplianceState;
  expiry_date: string | null;
  days_left: number | null;
  document_id: string | null;
  pending_document_id: string | null;
}

export interface ComplianceItem {
  supplier: { id: string; supplier_code: string; legal_name: string; supplier_type: string; status: string };
  state: ComplianceState;
  requirements: Requirement[];
  next_expiry: string | null;
  paid_last_90_days: string | number;
}

export interface ComplianceOverview {
  warning_days: number;
  suppliers: number;
  by_state: Record<ComplianceState, number>;
  awaiting_verification: number;
  paid_to_non_compliant_90_days: string | number;
  items: ComplianceItem[];
}

export interface SupplierDocument {
  id: string;
  doc_type: string;
  status: "UPLOADED" | "EXTRACTED" | "VERIFIED" | "REJECTED" | "EXPIRED";
  issue_date: string | null;
  expiry_date: string | null;
  original_filename: string | null;
  size_bytes: number | null;
  uploaded_at: string;
  verified_at: string | null;
  rejection_reason: string | null;
  has_file: boolean;
}

export interface SupplierDocuments {
  supplier: { id: string; legal_name: string; status: string };
  state: ComplianceState | null;
  requirements: Requirement[];
  documents: SupplierDocument[];
}
