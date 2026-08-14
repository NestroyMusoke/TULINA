# Phase 8 QA report

This report separates automated local proof from credentialed external proof. Local fixture tests exercise real application logic but do not claim a Gemini API or Google Cloud call.

## Automated matrix

| Area | Gate | Acceptance |
|---|---|---|
| Fixture integrity | `scripts/verify_phase0.py` | Original asset hashes, provenance, and nine canonical vectors remain intact |
| Domain/API/security/cloud adapters | Python unittest suite | Derived `TR-027`, policy/state gates, ADK runtime, intake, nine protocol vectors, roles, audit, Firestore/Pub/Sub/KMS doubles |
| Frontend components/protocol | Vitest | Routes, upload affordance, audit truth, Web Crypto and IndexedDB behavior |
| Canonical browser journey | Playwright | Card → six agents → DHO → note → offline receive → reconnect → duplicate/tamper/audit |
| Offline proof | Playwright request counter | Zero `/api/` requests during the receive moment |
| Failure recovery | Playwright route failure | Actionable service error and working Retry |
| Accessibility | axe-core in Chromium | No automated violations on District, Facility, and Audit routes after palette/landmark fixes |
| Responsive | Chromium 390 × 844 | Facility heading/navigation/device visible; horizontal overflow ≤ 1 px |
| Dependency security | `npm audit --audit-level=high` | No known npm advisories after the patched Vitest upgrade |
| Secret hygiene | `scripts/scan_secrets.py` | No high-confidence credentials or private keys in the project tree |
| Performance regression | `scripts/verify_phase8.py` | Raw production JS ≤ 1 MB, CSS ≤ 100 KB, HTML ≤ 15 KB |
| Deployment assets | `scripts/verify_phase7.py`, CI container jobs | Required Cloud Run/Firestore/Pub/Sub/KMS assets and both Docker builds configured |

## Findings repaired in Phase 8

- Darkened rust and muted text tokens to meet WCAG AA contrast on paper, card, green-soft, and impact backgrounds.
- Replaced the nested facility-phone `<main>` landmark with a presentation container, leaving one document main landmark.
- Added an allowlisted, role-protected offline-rejection report so the final tamper proof is auditable without uploading the signed note or applying stock.
- Upgraded Vitest to the patched major version; npm reports zero advisories.
- Added explicit hidden-process management for reliable Windows browser testing and isolated Chromium installation in CI.

## Manual review checklist

- [ ] Keyboard through skip link, navigation, role selector, details, demo controls, file inputs, network toggle, and Retry.
- [ ] Confirm visible focus is never clipped by sticky navigation or phone frames.
- [ ] Inspect 390 px, 768 px, 1024 px, and 1440 px views for text overlap and touch targets.
- [ ] Install the PWA and reload the facility shell after losing the network.
- [ ] Test camera permission denied, unreadable QR image, unsupported stock-card image in fixture mode, backend unavailable, and slow agent polling.
- [ ] Rehearse reset after a partially completed demo.
- [ ] Run the credentialed Cloud verification and inspect Cloud Logging correlation before the video.

## Honest limitations

- Automated axe checks do not replace assistive-technology and field usability testing.
- Bundle budgets measure built bytes, not end-user latency on a specific network/device.
- Local Chrome verifies the PWA behavior; camera hardware and install prompts vary by device/browser.
- Docker images are built in CI. A local Docker build still requires Docker Desktop’s Linux engine.
- Google Cloud/Gemini proof requires the owner’s project, billing, credentials, and final deployment; it cannot be truthfully completed in fixture mode.
