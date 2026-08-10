# Phase 2 — Judge-facing PWA

Phase 2 turns the deterministic domain engine into a rehearsable product without pretending later integrations exist.

## Delivered routes

- **Judge Demo** — four controlled moments backed by reset, discovery, request-approval, and approve endpoints.
- **District View** — the five-second product promise, the derived TR-027 recommendation, evidence, policy gates, metrics, actions, and live activity.
- **Medicine network** — searchable and filterable inventory positions across all 70 facility/product records.
- **Facility phone** — a responsive Busiu receiving view for `DEV-F02-01`, with unmistakable network status.
- **Audit trail** — plain-language events plus expandable trace and hash evidence.

## Server operations

The FastAPI app seeds its local SQLite repository from the canonical fixture through `DomainEngine`. It exposes health and readiness probes, overview/network/activity reads, deterministic reset and discovery, and the first two guarded workflow transitions. DHO approval requires the `dho_approver` role; invalid roles and skipped transitions are rejected.

## Honest boundary

This phase does not issue a QR note, verify a signature offline, run Google ADK, call Gemini, or deploy to Google Cloud. Those features remain unchecked in `PHASES.md` and arrive in their named phases. UI copy labels the operational records as synthetic demonstration data and contains no patient data.

## Verification

- Backend: domain, repository, state-machine, and API tests.
- Frontend: lint, three component/integration tests, and production TypeScript/Vite build.
- CI: separate locked backend and npm frontend jobs.

Run all current checks from the repository root with `./scripts/test.ps1` in PowerShell.
