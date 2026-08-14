# Tulina — Devpost draft

> Draft only. Nothing has been sent to Devpost. Official account registration, eligibility, live form fields, hosted URL, and video URL must be confirmed by the project owner.

## Title

Tulina

## One-line Summary

One clinic is empty. The district isn’t. Tulina’s background agents find safe medicine nearby, obtain human approval, and prove offline delivery.

## Category

Fortified Enterprise Fleet, with Taskmaster-level operational clarity.

## Problem

Medicine availability is often treated as a single-facility problem. In reality, one clinic may be out of an essential product while another nearby clinic has safe surplus or stock approaching expiry. Discovering that imbalance, checking whether a move is safe, finding the correct approver, preparing paperwork, and proving receipt can take fragmented calls and spreadsheets. Weak connectivity makes the final receiving step harder.

The result is avoidable stock-out time at one facility and avoidable expiry risk at another.

## Solution

Tulina is a district medicine-redistribution control plane, not a chatbot. A stock-card photo becomes a validated observation. A background Google ADK fleet watches the district, derives safe transfer candidates, checks deterministic policy, and pauses for a District Health Officer. After approval, Dispatch issues a signed one-use Tulina Note. A designated facility phone verifies it with cached public trust, signs a receipt in IndexedDB while offline, and checks in after reconnect. Reconciliation changes inventory exactly once and appends every material decision to a tamper-evident audit timeline.

The four-minute story derives transfer `TR-027`: 11 transfer packs of Oxytocin 10 IU/ml from Mbale Regional Referral Hospital to Busiu Health Centre IV, approved as `APR-DHO-001`.

## Why This Matters

Tulina converts a district’s existing stock into operational resilience. It can shorten the path from shortage to safe action, protect donor safety floors, prioritize early-expiry stock, preserve human clinical/governance authority, and keep receiving viable where connectivity is unreliable.

All operational values in this project are synthetic research-grade fixtures, not current facility data. No patient data is used.

## Features and Functionality

- Multimodal stock-card upload/camera intake with structured extraction, confidence, evidence, registry resolution, correction, and human confirmation.
- Six real Google ADK agents: Stock Intake, Watch, Match, Steward, Dispatch, and Reconciliation.
- Asynchronous queued workflows with durable run/tool-step state and visible progress—no chat prompt required.
- Deterministic cover, quantity, FEFO expiry, route, cold-chain, care-level, and authorization gates.
- Human-only DHO approval enforced by role permissions and workflow state.
- P-256 signed one-use QR Tulina Notes and cached public trust.
- Offline Web Crypto verification, non-exportable device key, IndexedDB receipt queue, and reconnect sync.
- Exactly-once inventory mutation; duplicate receipt retry applies zero.
- Rejection of tampering, local replay, wrong recipient, expiry, unknown issuer, malformed QR, invalid device signature, and unsafe conflicts.
- Redacted hash-chained audit history, request/trace/run IDs, structured logs, prompt-injection isolation, and guarded tool/model outputs.
- Installable, responsive District and facility PWA with deterministic Judge Demo controls.
- Credential-free fixture mode plus managed Cloud Run, Firestore, Pub/Sub, Vertex AI/Gemini, Cloud KMS, and Cloud Logging adapters.

## How We Used AI

Gemini 3.5 Flash or newer receives stock-card image bytes and returns a strict structured extraction containing fields, movements, confidence, and evidence. Tulina resolves identities and applies deterministic consistency/security checks before a facility worker may accept the observation.

Gemini also produces concise explanations from validated recommendation facts. It never receives approval, cryptographic, or inventory-mutation authority. Hidden model reasoning is neither requested nor displayed.

Google ADK provides the actual multi-agent hierarchy and runner. Each agent invokes named allowlisted tools and leaves durable events. Fixture mode executes the same ADK workflow but explicitly states that Gemini was not called.

## How We Used Codex

Codex was used as an engineering collaborator through eight deliberately separated phases: product constitution, deterministic domain foundation, PWA, ADK fleet, multimodal intake, offline protocol, security/cloud deployment, and release hardening. Each phase was tested before the repository owner created the commit.

Codex helped inspect the synthetic source pack, translate legacy product-facing labels without changing signed fixture integrity, implement typed Python/TypeScript boundaries, write adversarial and browser tests, diagnose CI/dependency issues, harden roles and audit events, and create reproducible Google Cloud scripts. The owner retained commit and push control.

## Architecture

The React/TypeScript PWA talks to FastAPI on Cloud Run. Google ADK coordinates six agents. Gemini handles multimodal interpretation and constrained explanation. Deterministic tools calculate stock and policy. Firestore persists inventory, transfer, workflow, intake, receipt, nonce, exception, and audit state. Pub/Sub delivers authenticated background work. Cloud KMS signs P-256 notes. The offline facility edge uses IndexedDB and Web Crypto.

- Mermaid: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Exportable image: [docs/architecture.svg](docs/architecture.svg)
- Agent/tool map: [docs/AGENT_FLEET.md](docs/AGENT_FLEET.md)

## Technologies Used

Python 3.12, FastAPI, Pydantic, Google ADK, Google Gen AI SDK, Gemini 3.5 Flash+, React 19, TypeScript, Vite, IndexedDB, Web Crypto, P-256 ECDSA, QR/ZXing, Playwright, axe-core, Cloud Run, Firestore, Pub/Sub, Vertex AI, Cloud KMS, Cloud Logging, Docker, Cloud Build, GitHub Actions.

## Other Data Sources Used

The repository imports the supplied synthetic/research-grade Tulina source pack: JSON records, Excel workbook, stock-card PNG, and dataset README. IDs and cryptographic fixtures are preserved. Fixture mode recognizes only the supplied PNG digest and replays its saved extraction instead of pretending to run vision on arbitrary images.

No patient data, live national stock feed, or current facility balance is included.

## Findings and Learnings

- The hard part is not finding surplus; it is preserving authority and donor safety while converting a recommendation into one verifiable action.
- Models are strongest at ambiguous perception and communication. Arithmetic, policy, workflow authority, cryptography, and idempotency benefit from deterministic boundaries.
- Offline receipt authority can be compact: cached public trust, recipient binding, a one-use nonce, and a non-exportable device key.
- “Exactly once” requires one transactional boundary across transfer state, inventory, receipt, nonce, idempotency, and audit—not a UI flag.
- Product-facing operational language makes multi-agent/security evidence understandable without hiding the technical proof judges need.

## Testing Instructions

Windows CMD:

```cmd
cd /d "C:\Users\X1 Yoga\Documents\Codex\2026-08-09\tulina"
copy .env.example .env
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\setup.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\test.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\dev.ps1"
```

Open `http://localhost:5173/judge`, reset the demo, and follow all eight moments. Fixture mode requires no credentials. The full gate covers backend/domain/security/cloud adapters, frontend protocols, the canonical offline browser journey, axe accessibility, failure retry, responsive layout, bundle budgets, dependency advisories, and secret scanning.

Cloud deployment and verification are documented in [docs/DEPLOYMENT_GCP.md](docs/DEPLOYMENT_GCP.md).

## Spin-up Instructions

1. Install Python 3.12+, Node.js 22+, npm, and Chrome.
2. Copy `.env.example` to ignored `.env`.
3. Run `scripts\setup.ps1`.
4. Run `scripts\dev.ps1`.
5. Open `/judge` and reset.
6. For Google Cloud, authenticate with `gcloud`, then run `infra\gcp\deploy.ps1 -ProjectId YOUR_PROJECT_ID`.
7. Run `infra\gcp\verify.ps1` and retain the successful proof for the video.

## Screenshot Shot List

1. District promise and `TR-027` Found nearby recommendation.
2. Stock-card photo with extraction confidence/evidence and confirmation.
3. Six-agent Google ADK run and deterministic decision panel.
4. Offline Busiu phone with Tulina Note and queued receipt.
5. Exactly-once before/after, duplicate/tamper audit, and Cloud Run proof.

## Demo Video

Approximately four minutes following [docs/DEMO_SCRIPT_4_MIN.md](docs/DEMO_SCRIPT_4_MIN.md): problem, multimodal intake, asynchronous agents, human approval, offline receiving, exactly-once reconnect, duplicate/tamper defense, and visible Google Cloud deployment proof.

Video URL: **TODO — add public or judge-accessible video URL.**

## Public Demo Link

**TODO — add the deployed `tulina-web` Cloud Run URL after credentialed verification.**

The hackathon requirements say a live URL is encouraged but clear Google Cloud deployment proof is mandatory even when the service is scaled down after recording.

## Public Repository Link

https://github.com/NestroyMusoke/TULINA

## Submission Readiness Notes

The local application and deployment automation are implemented. Fixture acceptance is reproducible without credentials. Before final submission, the owner must deploy/verify the Google Cloud revision, run one live Gemini extraction, record the four-minute demo, add the hosted/video URLs, confirm Devpost registration and eligibility, and paste the final form-specific copy.

## Known Limitations

- Synthetic stock records are not a live medicine information system.
- Demo role headers are explicit server-enforced authorization examples, not production workforce authentication.
- A real program needs organizational identity, device enrollment/revocation, policy ownership, local legal/regulatory review, data agreements, and field validation.
- Automated accessibility and Chrome tests do not replace assistive-technology, camera-hardware, or low-end-device field testing.
- Cloud/Gemini execution cannot be claimed until the owner’s credentialed project visibly proves it.
- Tulina is a transfer-coordination prototype, not prescribing, dispensing, or clinical decision software.

## TODO Official Form Fields

- Hosted project URL
- Demo video URL
- Final team/individual details
- Devpost registration and eligibility confirmation
- Exact live Gemini model/region shown in the video
- Google Cloud project proof and deployed revision date
- Optional public content/social links and required hackathon wording/hashtag
- Codex session ID only if the authenticated official form explicitly asks for one; confirm the correct session with the owner before recording it

