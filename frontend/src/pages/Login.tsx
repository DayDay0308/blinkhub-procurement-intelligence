import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Button, ErrorNote, Field, inputCls } from "../components/ui";
import { useAuth } from "../lib/auth";

const DEMO_PASSWORD = "Demo@2026!";

/** Demo accounts, grouped by what each person does in the story. */
const DEMO = [
  { email: "manager@mics.demo", who: "Mpho, Manager", does: "Sees every dashboard; receives escalations" },
  { email: "finance@mics.demo", who: "Farid, Finance officer", does: "Captures emailed invoices, releases payments" },
  { email: "approver@mics.demo", who: "Anele, Approver", does: "Approves invoices routed to her" },
  { email: "procurement@mics.demo", who: "Palesa, Procurement officer", does: "Records deliveries, registers suppliers" },
  { email: "auditor@mics.demo", who: "Aisha, Auditor", does: "Investigates risk flags" },
  { email: "accounts@ubuntucleaning.demo", who: "Ubuntu Cleaning (SMME)", does: "Supplier portal: submits and tracks invoices" },
  { email: "accounts@thutosupplies.demo", who: "Thuto Supplies (SMME)", does: "Supplier portal" },
];

export function Login() {
  const { user, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const go = async (e?: FormEvent, as?: string) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(as ?? email, as ? DEMO_PASSWORD : password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <div className="flex flex-col justify-between bg-ink p-8 text-white md:p-12">
        <div>
          <div className="text-xl font-bold">Blink</div>
          <div className="text-white/70">Procurement intelligence</div>
        </div>
        <div className="max-w-md py-12">
          <h1 className="text-3xl font-bold leading-tight md:text-4xl">Every invoice has an owner. Every rand is accounted for.</h1>
          <p className="mt-4 text-white/75">
            Invoice tracking against 30-day terms, explainable risk flags and supplier scorecards for
            Mzansi Infrastructure &amp; Community Services.
          </p>
        </div>
        <p className="text-sm text-white/55">
          Candidate prototype for the BlinkHub Procurement Innovation Challenge. Case-study sample data plus a
          clearly labelled synthetic demonstration year.
        </p>
      </div>

      <div className="flex items-center justify-center p-6 md:p-12">
        <div className="w-full max-w-md">
          <h2 className="text-xl font-bold">Sign in</h2>
          <form onSubmit={go} className="mt-5 space-y-4">
            <Field label="Email">
              <input className={inputCls} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Password">
              <input className={inputCls} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <ErrorNote error={error} />
            <Button type="submit" disabled={busy} className="w-full">{busy ? "Signing in…" : "Sign in"}</Button>
          </form>

          <h3 className="mt-10 text-sm font-semibold">Or sign in as a demo user</h3>
          <ul className="mt-2 divide-y divide-line-soft rounded-lg border border-line bg-surface">
            {DEMO.map((d) => (
              <li key={d.email}>
                <button type="button" disabled={busy} onClick={() => go(undefined, d.email)} className="w-full px-4 py-2.5 text-left hover:bg-paper disabled:opacity-50">
                  <div className="text-sm font-semibold">{d.who}</div>
                  <div className="text-xs text-muted">{d.does}</div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
