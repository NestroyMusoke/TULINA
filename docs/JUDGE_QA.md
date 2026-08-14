# Judge Q&A

## What problem does Tulina solve?

A facility can be out of a medicine while another nearby facility has safe surplus or an early-expiry batch. Tulina turns that district-wide imbalance into a governed transfer proposal and verifiable delivery instead of leaving staff to discover it through calls and spreadsheets.

## Is `TR-027` hard-coded in the interface?

No. The importer preserves canonical IDs, and the domain engine derives the 11-pack match from facility stock, monthly use, safety floors, expiry order, route, care level, and cold-chain data. The UI renders repository state. Tests fail if the calculation is replaced by the expected fixture output.

## Are the agents real or decorative?

They are real Google ADK `BaseAgent` children under `tulina_fleet`, executed by an ADK `Runner`. A queued inventory event persists a durable run and six named tool steps. Partial progress is visible without a chat prompt. Fixture mode uses the same ADK/tool/state path while clearly reporting that Gemini was not called.

## What does Gemini do?

Gemini 3.5 Flash or newer performs structured multimodal stock-card extraction and concise explanation from validated facts. Output crosses strict schemas, confidence checks, registry resolution, tool guards, and human correction. Gemini cannot approve, sign, verify, dispatch, or mutate inventory.

## Why six agents instead of one large prompt?

Each responsibility has a distinct authority and failure boundary: intake interprets, watch detects, match ranks, steward governs, dispatch signs only after approval, and reconciliation handles signed receipts. Durable step records show exactly where work paused or failed.

## Where does the human retain authority?

A facility worker confirms uncertain or high-confidence extracted observations. Only the DHO role can approve the transfer and issue its note. The workflow state machine independently prevents a permitted caller from skipping required states.

## How is offline receiving real?

The phone caches a public P-256 trust bundle. Web Crypto verifies the note locally and IndexedDB stores a device-signed receipt using a non-exportable private key. The E2E test counts API requests and proves the receive moment makes zero. Reconciliation happens only after reconnect.

## How is exactly-once delivery enforced?

The receipt ID, note nonce, transfer state, and inventory mutation share one repository transaction. Firestore uses retryable transactions in GCP mode; SQLite provides the same invariant locally. A duplicate returns `IDEMPOTENT_ACK`, records “Duplicate applied zero,” and leaves the mutation count at one.

## What happens on tampering or replay?

Changed signed content fails the P-256 check before a receipt is created. Local nonce replay is blocked. Wrong recipient, expiry, unknown issuer, malformed QR, invalid device signature, and cloud conflicts fail closed. An allowlisted edge report records the rejection without uploading the signed token; conflicts enter human review without mutation.

## Is the audit log immutable?

Events are canonically hashed with the prior event hash. Readiness and the Audit view recompute the chain instead of assuming validity. Firestore updates the audit head transactionally. This is tamper-evident application evidence, not a claim of a blockchain or statutory records system.

## How does this fit Fortified Enterprise Fleet?

- Registry: explicit versioned fleet catalog and capability metadata.
- Runtime/state: ADK plus durable Firestore workflow/step records.
- Identity/gateway: separate Cloud Run service identities, authenticated Pub/Sub OIDC, server permission matrix, strict contracts.
- Model armor: OCR instruction isolation, denied tool keys, size limits, schema validation, no model authority.
- Observability: structured logs, request/trace/run IDs, named tool events, hash-chained audit evidence.

## What Google Cloud services are used?

Cloud Run hosts the API and web app. Firestore stores operational state. Pub/Sub delivers asynchronous agent work. Vertex AI provides Gemini. Cloud KMS signs P-256 Tulina Notes. Cloud Logging captures correlated JSON events.

## Is any real facility or patient data present?

No patient data exists. Facility/stock records are synthetic research-grade fixtures and every operational screen labels them as synthetic, not current stock. Product-facing legacy source names were translated without changing signed fixture bytes or IDs.

## What is production-ready, and what is still demo-only?

The deterministic engine, contracts, agent orchestration, offline cryptography, idempotency, cloud adapters, audit boundaries, containers, deployment automation, and tests are implemented. Demo role headers are not workforce authentication. A real rollout still needs verified organizational identity, device enrollment/revocation operations, local regulatory validation, data-governance agreements, clinical ownership, and field usability work.

## How can I reproduce the main claim?

Run `scripts\setup.ps1`, `scripts\dev.ps1`, open `/judge`, reset, and follow the eight moments. Run `scripts\test.ps1` for the automated proof. The Playwright test asserts the exact stock changes, offline network silence, duplicate zero, tamper rejection, accessibility, failure retry, and phone layout.
