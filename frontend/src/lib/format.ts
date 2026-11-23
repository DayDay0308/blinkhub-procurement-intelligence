const rand = new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR", maximumFractionDigits: 0 });
const randCents = new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR", minimumFractionDigits: 2 });

/** R1 330 000 */
export const money = (v: string | number | null | undefined) => (v == null ? "-" : rand.format(Number(v)));

/** R33 340,82 */
export const moneyExact = (v: string | number) => randCents.format(Number(v));

/** R4.03m, R955k: for headline figures */
export function moneyShort(v: string | number | null | undefined): string {
  if (v == null) return "-";
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return `R${(n / 1e6).toFixed(n >= 1e8 ? 0 : 2)}m`;
  if (Math.abs(n) >= 1e3) return `R${Math.round(n / 1e3)}k`;
  return `R${Math.round(n)}`;
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export const pct = (v: number | null | undefined, digits = 1) => (v == null ? "-" : `${(v * 100).toFixed(digits)}%`);

export const date = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" }) : "-";

export const dateTime = (v: string) =>
  new Date(v).toLocaleString("en-ZA", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** "PENDING_APPROVAL" -> "Pending approval" */
export const label = (v: string) => {
  const s = v.replaceAll("_", " ").replace(/last4/i, "(last 4 digits)").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
};

export const PROVINCES: Record<string, string> = {
  GAUTENG: "Gauteng", LIMPOPO: "Limpopo", KWAZULU_NATAL: "KwaZulu-Natal", MPUMALANGA: "Mpumalanga",
  NORTH_WEST: "North West", FREE_STATE: "Free State", EASTERN_CAPE: "Eastern Cape",
  WESTERN_CAPE: "Western Cape", NORTHERN_CAPE: "Northern Cape",
};

/** Plain-language explanations of 3-way-match exception codes. */
export const EXCEPTIONS: Record<string, string> = {
  MISSING_PO_REFERENCE: "No purchase order number, so it can't be matched to an order",
  AWAITING_GOODS_RECEIPT: "Waiting for proof of delivery (goods receipt)",
  EXCEEDS_GOODS_RECEIVED: "Bills more than has been delivered so far",
  AMOUNT_EXCEEDS_PO: "Bills more than the purchase order value",
  PO_NOT_APPROVED: "The purchase order isn't approved",
  NO_ACCOUNTABLE_APPROVER: "Nobody is responsible for approving it",
};

export const ROLE_LABEL: Record<string, string> = {
  ADMIN: "Administrator", PROCUREMENT_OFFICER: "Procurement officer", FINANCE_OFFICER: "Finance officer",
  APPROVER: "Approver", MANAGER: "Manager", AUDITOR: "Auditor", SUPPLIER: "Supplier",
};
