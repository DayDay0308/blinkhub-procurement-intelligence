# Blink web app (React)

Vite + React 18 + TypeScript, Tailwind CSS 4, TanStack Query, React Router, Recharts.

```powershell
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
npm run typecheck
npm test
npm run build
```

In Docker the app is served by nginx on http://localhost:8080 and `/api` is proxied to the
`api` container, so the browser only ever talks to one origin.

Design: Public Sans with tabular figures; ink navy for structure; SMME orange and
large-enterprise blue match the Power BI report; green/amber/red only ever mean state.
The signature element is the 30-day payment-terms ruler (`src/components/TermsRuler.tsx`).
