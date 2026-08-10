# Tulina

**One clinic is empty. The district isn’t.**

Tulina is a medicine redistribution PWA for district health teams. Background agents discover a shortage and nearby safe surplus, deterministic policy tools propose a transfer, a human District Health Officer approves it, and a signed one-use Tulina Note proves delivery even when the receiving phone is offline.

All operational balances are synthetic demonstration fixtures. The repository contains no patient data and no private signing keys.

## Quick start (Windows PowerShell)

```powershell
Copy-Item .env.example .env
.\scripts\setup.ps1
.\scripts\dev.ps1
```

Open `http://localhost:5173/judge`. Fixture mode needs no keys. Choose the visible **Reset demo** button before a rehearsal.

## What is real today

- The recommendation is recalculated from imported facility, stock, consumption, route, expiry, and policy records.
- The Judge Demo reset, discovery, approval request, and DHO approval call the FastAPI service and durable state machine.
- District, network, facility, and audit routes render server data with clear synthetic-data labeling.
- Approval is role-protected on the server and each change appends to a hash-chained event history.

The ADK/Gemini fleet, multimodal intake, offline Tulina Note, and Google Cloud adapters are deliberately scheduled for later phases; see [PHASES.md](PHASES.md). They will activate only through environment variables while fixture mode remains credential-free.

## Repository map

- `backend/` — FastAPI, deterministic domain engine, repositories, agent runtime, security protocol.
- `frontend/` — React/TypeScript installable PWA with District and facility routes.
- `contracts/` — versioned JSON Schemas shared across runtimes.
- `data/fixtures/` — imported read-only source pack with unchanged cryptographic records.
- `docs/` — product, security, deployment, demo, and submission documentation.
- `infra/` — Cloud Run, Firestore, Pub/Sub, IAM, and optional KMS deployment assets.

## Verification

```powershell
.\scripts\test.ps1
```

To inspect the Phase 1 calculations directly:

```powershell
python -m backend.tulina.cli recommend
.\scripts\seed.ps1
```

See [PHASES.md](PHASES.md) for the acceptance checklist and [Phase 2 implementation notes](docs/PHASE_2_UI.md) for the current UI/API boundary.
