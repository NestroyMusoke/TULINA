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

Cloud Run, Firestore, Pub/Sub, Vertex AI/Gemini, and optional Cloud KMS are the submission architecture. The generic Sites hosting path is intentionally not used because it would replace the required GCP topology.

## 006 — ADK orchestrates; durable stores remain authoritative

Tulina uses a Google ADK parent/child hierarchy and Runner for actual multi-agent execution. Invocation state is convenient for passing validated results between agents, but durable run, tool-step, transfer, and audit records remain in repository adapters so restarts do not erase operational evidence.

## 007 — Gemini explains validated facts only

Gemini 3.5 Flash or newer creates a concise structured explanation from deterministic recommendation evidence. It never receives authority to approve, issue a Tulina Note, reconcile a receipt, or mutate medicine stock. Invalid model output fails closed.

## 008 — Image interpretation is provisional until a person confirms it

The Stock Intake Agent may transcribe a card, but deterministic registry and consistency checks decide whether the output is usable. Low-confidence or conflicting fields are blocked behind correction. Even a high-confidence extraction remains provisional until a facility worker accepts it; Gemini never updates inventory directly.

Fixture mode recognizes only the supplied synthetic image by SHA-256 and replays a saved extraction with the same contract as live Gemini. Uploaded image bytes remain invocation-scoped and are discarded after extraction; durable records retain only the image digest and structured evidence.
