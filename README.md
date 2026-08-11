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

If Windows blocks local PowerShell scripts, run them with
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1`
and the same form for `dev.ps1` or `test.ps1`.

Open `http://localhost:5173/judge`. Fixture mode needs no keys. Choose the visible **Reset demo** button before a rehearsal.

## What is real today

- The recommendation is recalculated from imported facility, stock, consumption, route, expiry, and policy records.
- The Judge Demo reset, discovery, approval request, and DHO approval call the FastAPI service and durable state machine.
- A six-agent Google ADK hierarchy runs from a queued background event without a chat prompt and persists every agent/tool step.
- The Stock Intake Agent accepts camera/file images, invokes a validated multimodal extraction tool, displays confidence and evidence, and requires facility-worker confirmation.
- Fixture mode faithfully replays only the supplied card by SHA-256; live mode sends image bytes to Gemini 3.5 Flash through the official Google Gen AI SDK.
- A local durable queue and a Pub/Sub publisher adapter share the same versioned run contract.
- District, network, facility, and audit routes render server data with clear synthetic-data labeling.
- Approval is role-protected on the server and each change appends to a hash-chained event history.
- The ADK Dispatch Agent issues a real P-256 QR Tulina Note; the facility PWA verifies it offline with cached trust, signs a receipt with a non-exportable Web Crypto key, queues it in IndexedDB, and reconnects through the ADK Reconciliation Agent.
- Reconciliation applies the inventory change exactly once. Duplicate upload applies zero; tampering, replay, wrong recipient, expiry, unknown issuer, malformed payload, and cloud-state conflict are rejected or quarantined by the nine canonical vectors.

Production governance hardening and Google Cloud deployment remain in later phases; see [PHASES.md](PHASES.md). Fixture mode remains credential-free and never claims that Gemini was called.

## Repository map

- `backend/` — FastAPI, deterministic domain engine, repositories, agent runtime, security protocol.
- `frontend/` — React/TypeScript installable PWA with District and facility routes.
- `contracts/` — versioned JSON Schemas shared across runtimes.
- `data/fixtures/` — imported read-only source pack with unchanged cryptographic records.
- `docs/` — product, security, deployment, demo, and submission documentation.
- `infra/` — Cloud Run, Firestore, Pub/Sub, IAM, and optional KMS deployment assets.

## Verification

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

To inspect the Phase 1 calculations directly:

```powershell
python -m backend.tulina.cli recommend
.\scripts\seed.ps1
```

To prove the Phase 3 fleet runs asynchronously without a chat prompt:

```powershell
python -m backend.tulina.agents.cli --database work/agent-cycle.sqlite3 --reset
```

For live Gemini API mode, set `TULINA_MODE=gemini` and paste `GOOGLE_API_KEY` into `.env`. For Vertex AI, set `TULINA_MODE=gcp`, `GOOGLE_GENAI_USE_VERTEXAI=true`, and `GOOGLE_CLOUD_PROJECT`. Startup rejects missing credentials and Gemini models older than 3.5.

See [PHASES.md](PHASES.md), [the agent fleet guide](docs/AGENT_FLEET.md), [the stock-card intake guide](docs/STOCK_CARD_INTAKE.md), and [the offline protocol guide](docs/OFFLINE_PROTOCOL.md) for the current runtime boundary.
