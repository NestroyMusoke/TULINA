# Decisions

## 001 — Vite PWA plus FastAPI

Vite keeps the facility client small and makes service-worker/IndexedDB behavior direct. FastAPI provides typed contracts and fits ADK/GCP Python libraries. Both containers deploy independently to Cloud Run.

## 002 — Models advise; code governs

Gemini handles multimodal interpretation and concise explanations. Inventory arithmetic, coverage, routes, cold-chain policy, state transitions, signatures, replay protection, and idempotency are deterministic and tested.

## 003 — Ports for credentials-free use

Fixture/local adapters implement the same repository, queue, model, and signer ports as Firestore, Pub/Sub, Gemini, and KMS. No-key mode demonstrates real calculations and security verification without claiming a cloud call occurred.

## 004 — Preserve cryptographic fixtures

Legacy names remain inside canonical signed payloads. They are translated only at presentation boundaries so existing signatures remain verifiable.

## 005 — Deployment target

Cloud Run, Firestore, Pub/Sub, Vertex AI/Gemini, and Cloud KMS are the submission architecture. The generic Sites hosting path is intentionally not used because it would replace the required GCP topology. Cloud KMS remains absent from credential-free local mode but is required by the managed GCP runtime so an ephemeral container never owns the issuer private key.

## 006 — ADK orchestrates; durable stores remain authoritative

Tulina uses a Google ADK parent/child hierarchy and Runner for actual multi-agent execution. Invocation state is convenient for passing validated results between agents, but durable run, tool-step, transfer, and audit records remain in repository adapters so restarts do not erase operational evidence.

## 007 — Gemini explains validated facts only

Gemini 3.5 Flash or newer creates a concise structured explanation from deterministic recommendation evidence. It never receives authority to approve, issue a Tulina Note, reconcile a receipt, or mutate medicine stock. Invalid model output fails closed.

## 008 — Image interpretation is provisional until a person confirms it

The Stock Intake Agent may transcribe a card, but deterministic registry and consistency checks decide whether the output is usable. Low-confidence or conflicting fields are blocked behind correction. Even a high-confidence extraction remains provisional until a facility worker accepts it; Gemini never updates inventory directly.

Fixture mode recognizes only the supplied synthetic image by SHA-256 and replays a saved extraction with the same contract as live Gemini. Uploaded image bytes remain invocation-scoped and are discarded after extraction; durable records retain only the image digest and structured evidence.

## 009 — Offline authority is public-key verifiable, not model-dependent

Tulina signs canonical note and receipt payloads with P-256 and verifies them using deterministic cryptographic libraries. The browser caches issuer public trust and owns a non-exportable device private key; Gemini and ADK never receive key material. ADK Dispatch and Reconciliation Agents invoke allowlisted signing/reconciliation tools, while the tools and durable state machine retain action authority. Local signer material is generated into ignored runtime storage; production replaces that signer with Cloud KMS.

## 010 — One permission matrix, separate workflow invariants

Every protected API operation maps to a named `Action` and a server-side role permission set. The state machine remains an independent second boundary: even a permitted DHO request cannot skip required transfer states. Fixture headers keep the demo credentials-free and are explicitly not presented as production authentication.

## 011 — Evidence is concise, correlated, and redacted before hashing

Tulina persists validated facts, named tool events, actors, status changes, and hashes—not model prompts or hidden reasoning. Request correlation is added to audit details, then sensitive keys and raw payloads are redacted before canonical hashing. Quarantine acknowledgement records human review but deliberately has no path to mutate inventory.
