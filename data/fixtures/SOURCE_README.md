# MÖBIUS Relay Demo Dataset v2

This version preserves the v1 Uganda evidence, facilities, products, synthetic inventory, commitments, routes, transfers and benchmarks, and adds the complete offline Relay protocol data needed for implementation and acceptance testing.

## Main acceptance story

- Transfer: TR-027
- Donor: F01 — Mbale Regional Referral Hospital
- Recipient: F02 — Busiu Health Centre IV
- Product: P05 — Oxytocin 10 IU/ml
- Batch: BAT-F01-P05-01 / OXY-MBL-2610A
- Quantity: 11 transfer packs
- Human approval: APR-DHO-001
- Capsule: CAP-TR027-001
- Recipient device: DEV-F02-01

The phone verifies the signed capsule while offline, creates a signed receipt, shows one pending item, then automatically reconciles after connectivity returns. The main run applies exactly one transfer mutation; the duplicate retry applies zero.

## Added datasets

- Agent Registry: versioned facility, coordinator, approval and reconciliation agents
- Device Registry: designated devices and cached public trust bundle
- Relay Capsules: canonical payload, public key, hash and real P-256 signature fixture
- Offline Receipts: happy path and all edge rejection decisions
- Sync Ledger: simultaneous edge/cloud state and idempotent reconciliation
- Relay Test Vectors: nine reproducible acceptance and adversarial cases
- RELAY DEMO: formula-driven judge-facing proof

## Cryptographic safety

The workbook and JSON contain only public keys and signed test fixtures. No private key is written to disk. Production capsule issuance must use Cloud KMS; recipient receipt keys should be generated as non-exportable Web Crypto keys.

## Truth statement

Facility identities, medicine rules, policy sources and public evidence remain source-backed. Inventory, consumption, devices, cryptographic identities, events and disruptions are explicitly synthetic development fixtures. There is no patient data, and the dataset does not claim current stock at any named health facility.
