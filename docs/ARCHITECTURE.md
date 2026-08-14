# Architecture

Tulina is a Vite/React PWA backed by Python 3.12/FastAPI. A repository port selects local SQLite-like fixture persistence or Firestore. A queue port selects an in-process durable demo queue or Pub/Sub. Google ADK coordinates six agents; every proposed action crosses validated Pydantic contracts and deterministic tools before it can change workflow state.

```mermaid
flowchart LR
  Phone["Facility PWA · offline IndexedDB"] -->|"signed receipt"| API["FastAPI on Cloud Run"]
  District["District View PWA"] --> API
  API --> Runtime["ADK fleet runtime"]
  Runtime --> Gemini["Gemini 3.5 Flash"]
  Runtime --> Tools["Validated deterministic tools"]
  Runtime <--> Queue["Pub/Sub or local queue"]
  API <--> Store["Firestore or local repository"]
  Tools --> KMS["Cloud KMS signer or safe dev signer"]
  Store --> Audit["Hash-chained audit + agent timeline"]
```

## Fleet responsibilities

| Agent | Invokes | Asynchronous responsibility | Durable output |
|---|---|---|---|
| Stock Intake | Gemini vision, schema validator | Extract stock-card observations | observation + evidence + confidence |
| Watch | coverage and expiry tools | Detect shortage/surplus windows | finding |
| Match | quantity, route, cold-chain tools | Rank safe transfers | recommendation |
| Steward | policy and authorization tools | Block unsafe proposals; request DHO decision | approval request or exception |
| Dispatch | signer and trust bundle | Issue one-use Tulina Note after approval | signed note + nonce |
| Reconciliation | verifier and idempotent mutation | Apply valid receipts once; quarantine conflicts | receipt result + inventory event |

Humans retain correction authority for uncertain intake and sole approval authority for transfers.

## Phase 1 implementation boundary

The domain package is independent of FastAPI, Gemini, ADK, and GCP credentials. Pydantic models mirror the language-neutral JSON Schemas in `contracts/v1`. The `DomainEngine` converts private fixture records into stock positions, watch signals, policy decisions, ranked recommendations, and metrics. `SQLiteRepository` is the durable local adapter and provides transactionally consistent state, idempotency, and hash-chained audit history. The Phase 7 Firestore adapter implements the same port without changing these rules.

## Phase 2 implementation boundary

FastAPI now exposes the derived district overview, network positions, activity history, deterministic demo reset, discovery, approval request, and DHO approval. The React PWA consumes those endpoints through a typed service layer. The interface never calculates or embeds the TR-027 outcome: it renders the repository state produced by the Phase 1 domain engine.

The Judge Demo is an orchestrated UI over real operations. Demo headers make authorization visible, while the server remains the source of truth for permitted roles and workflow transitions.

## Phase 3 implementation boundary

`tulina_fleet` is a real Google ADK parent agent with six registered `BaseAgent` children. ADK's `Runner` invokes them in an explicit sequence and shares only validated invocation state. Every child calls a named ADK `FunctionTool`; tool outputs cross strict Pydantic boundaries before becoming durable state or UI evidence.

FastAPI accepts a versioned watch request, persists it as `QUEUED`, returns HTTP 202, and processes local jobs after the response. The PWA polls the durable run and renders partial agent/tool progress. Pub/Sub mode publishes the same run record for an authenticated Cloud Run push worker. SQLite or Firestore persists authoritative job and step state; ADK's in-memory session is invocation-scoped and is not treated as the system of record.

Gemini is deliberately outside the action boundary. In live mode it receives only validated recommendation facts and returns a `DecisionExplanation`; it cannot approve, dispatch, or mutate inventory. Fixture mode returns the same schema without credentials and the agent registry explicitly reports that no Gemini call occurred.

## Phase 4 implementation boundary

Camera and file uploads enter a dedicated ADK `stock_intake_agent`, which invokes the `extract_stock_card` function tool. The tool selects either the Gemini multimodal provider or the saved fixture provider, validates the structured result, resolves facility/product/batch IDs against registries, and persists an intake record. The ADK session is deleted after each invocation, so raw image bytes are not retained in application state; only the filename, MIME type, size, SHA-256 digest, structured extraction, evidence, and corrections remain.

The fixture provider is bound to the supplied synthetic PNG digest and refuses any other image instead of pretending it performed vision. Gemini output crosses the same `RawStockCardExtraction` contract. Confidence below 0.85, missing evidence, unknown identities, ledger inconsistencies, batch/expiry conflicts, or storage-range conflicts move the record to `NEEDS_REVIEW`. A facility worker must correct those fields and explicitly accept every observation before an `inventory_event` may start the district watch.

## Phase 5 implementation boundary

Dispatch and reconciliation are dedicated real ADK agent invocations over validated function tools. Models never sign, approve, verify, or mutate medicine. `ProtocolService` owns canonical encoding, P-256 checks, identity binding, replay decisions, and reconciliation. SQLite persists the local signer and protocol state; Firestore persists cloud notes, public device registrations, receipts, consumed nonces, outcomes, and exceptions while Cloud KMS retains the non-exportable issuer key.

The facility PWA caches only public issuer trust in IndexedDB and keeps its non-exportable Web Crypto private key locally. Offline scanning uses Web Crypto and a local nonce set without calling FastAPI or Gemini. Reconnection uploads the signed receipt; the repository transaction and idempotency ledger apply at most one inventory mutation. A cloud-state conflict is quarantined instead of merged.

## Phase 6 implementation boundary

FastAPI now enforces a central role-to-action permission matrix. Request middleware validates or creates correlation IDs, returns them to clients, emits body-free structured JSON logs, and binds request correlation to hash-chained business events. Problem responses are stable and carry a request reference without returning stack traces.

Audit details pass through recursive secret/raw-input redaction before hashing. The server recomputes chain status for readiness and the Audit view. OCR remarks are scanned as untrusted content and instruction-like text is isolated while inventory facts remain under deterministic and human checks. Every ADK tool result passes an allowlisted size/key boundary and strict model validation before it becomes state.

Quarantined cloud/edge conflicts have a durable, DHO-only `ACKNOWLEDGE_NO_MUTATION` resolution. Auditors are read-only, repeated resolutions are idempotent, and recovery never creates a second inventory write. `docs/SECURITY.md`, `docs/GOVERNANCE.md`, and `docs/OBSERVABILITY.md` define the controls and honest local-mode limits.

## Phase 7 implementation boundary

`TULINA_REPOSITORY=firestore` selects one Firestore environment root with dedicated collections for inventory, transfers, idempotency, audit, agent runs/steps, stock-card intakes, notes, devices, receipts, nonces, reconciliation results, and exception resolutions. Transfer delivery and the audit-chain head are updated in retryable Firestore transactions. The same receipt key therefore remains exactly once across Cloud Run instances.

`TULINA_QUEUE=pubsub` publishes a validated durable `AgentRun`. Pub/Sub pushes an OIDC-authenticated envelope to the internal worker route; the API verifies audience, service-account email, schema, trace identity, and immutable run fields before claiming the Firestore run. Redelivery of a completed run is acknowledged without rerunning it.

Cloud KMS signs a SHA-256 digest using `EC_SIGN_P256_SHA256`. The adapter verifies response identity/CRC32C, converts the DER signature to the browser protocol's 64-byte P1363 form, and exposes only the public JWK. Two non-root containers deploy independently to Cloud Run with startup/liveness probes, scale-to-zero limits, structured Cloud Logging, and separate service identities. See `docs/DEPLOYMENT_GCP.md` and `docs/IAM_GCP.md`.

## Phase 8 implementation boundary

Playwright drives the canonical `TR-027` journey against the real FastAPI service and PWA in fixture mode. It proves the stock-card gate, six persisted ADK steps, DHO authority, P-256 note issuance, zero API calls during offline receiving, IndexedDB receipt persistence, reconnect reconciliation, exactly one mutation, duplicate zero, tamper rejection, and the final hash-chained audit record. Separate browser checks cover failure/retry behavior, axe accessibility on the district/facility/audit routes, and 390 px phone overflow.

CI installs an isolated Chromium runtime after the backend and frontend gates pass. The local Windows runner may use installed Chrome and manages API/Vite processes explicitly. Release verification also rejects high-confidence secrets and enforces raw production budgets of 1 MB JavaScript, 100 KB CSS, and 15 KB HTML. These are regression budgets, not claims about network performance on a particular Ugandan connection.

The final architecture is available as this Mermaid source and as `docs/architecture.svg`. Credentialed proof remains deliberately separate: `infra/gcp/verify.ps1` must show the real Cloud Run URLs, Gemini provider, Firestore, Pub/Sub, and KMS state before those claims enter the video.
