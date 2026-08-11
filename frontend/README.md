# Tulina PWA

The Vite/React frontend is a responsive, installable district medicine coordination app. It reads live state from the FastAPI service; no transfer outcome is embedded in a component.

## Routes

- `/judge` — deterministic eight-moment walkthrough from stock-card intake through offline receipt, reconciliation, duplicate, and tamper proof.
- `/district` — operational overview, recommendation, approval, metrics, and activity.
- `/intake` — camera/file stock-card capture, evidence, correction, and human confirmation.
- `/network` — searchable stock positions across the synthetic district fixture.
- `/facility` — responsive Busiu receiving view with real QR camera/file scan, offline Web Crypto checks, IndexedDB queue, and reconnect sync for `DEV-F02-01`.
- `/audit` — plain-language and technical event history.

Run `npm run dev`, `npm run lint`, `npm run test`, or `npm run build` from this directory. The root PowerShell scripts run both frontend and backend for the normal Windows setup.
