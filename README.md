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
- A central server permission matrix keeps auditors read-only, request/trace IDs connect JSON logs to redacted hash-chain events, instruction-like OCR text is quarantined, and DHO exception acknowledgement is idempotent with zero stock mutation.
- GCP mode replaces every operational SQLite store with Firestore, claims Pub/Sub-delivered runs transactionally, verifies the push OIDC identity, and signs Tulina Notes through Cloud KMS.
- Non-root API/web containers, Cloud Build definitions, health probes, least-privilege service identities, guarded seed/teardown commands, and a read-only cloud proof script are ready for Cloud Run.

Fixture mode remains credential-free and never claims that Gemini or Google Cloud was called. A real cloud proof still requires the user's Google Cloud project, billing, and credentials; the repository does not fabricate that external state. The public hackathon deployment retains explicit demo-role headers and must add verified workforce identity before real operations.

## Repository map

- `backend/` — FastAPI, deterministic domain engine, repositories, agent runtime, security protocol.
- `frontend/` — React/TypeScript installable PWA with District and facility routes.
- `contracts/` — versioned JSON Schemas shared across runtimes.
- `data/fixtures/` — imported read-only source pack with unchanged cryptographic records.
- `docs/` — product, security, deployment, demo, and submission documentation.
- `infra/` — Cloud Run, Firestore, Pub/Sub, IAM, and Cloud KMS deployment assets.

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

For live Gemini API mode, set `TULINA_MODE=gemini` and paste `GOOGLE_API_KEY` into `.env`. Complete GCP mode requires Firestore, Pub/Sub push identity/audience, Vertex AI, and a full Cloud KMS key-version resource; `infra/gcp/deploy.ps1` creates and wires them without service-account keys. Startup rejects missing adapters/identity and Gemini models older than 3.5.

See [Google Cloud deployment](docs/DEPLOYMENT_GCP.md), [IAM](docs/IAM_GCP.md), [cost control](docs/COST_CONTROL.md), [PHASES.md](PHASES.md), [the security model](docs/SECURITY.md), [the governance guide](docs/GOVERNANCE.md), [the observability guide](docs/OBSERVABILITY.md), [the agent fleet guide](docs/AGENT_FLEET.md), [the stock-card intake guide](docs/STOCK_CARD_INTAKE.md), and [the offline protocol guide](docs/OFFLINE_PROTOCOL.md).
