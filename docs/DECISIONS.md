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

