# Offline Tulina Note protocol

## Purpose

The Tulina Note authorizes one documented transfer to one receiving facility for a limited time. It is not a prescription, dispensing record, or patient record. Every value in the acceptance story is synthetic demonstration data.

## Issue and receive sequence

1. The DHO records `APR-DHO-001`; the state machine moves `TR-027` to `APPROVED`.
2. The real Google ADK `dispatch_agent` invokes `issue_signed_tulina_note`. Deterministic code validates the state, creates the canonical payload, signs it with ECDSA P-256/SHA-256, stores it, and moves the transfer through `NOTE_ISSUED` to `IN_TRANSIT`.
3. While connected, `DEV-F02-01` caches the public trust bundle in IndexedDB, creates a non-exportable Web Crypto P-256 private key, and registers only its public JWK.
4. Offline, the PWA scans the QR and independently checks parse, trusted issuer, signature, recipient `F02`, issue/expiry time, and the local one-use nonce set. No API, Gemini call, or model judgment is involved.
5. On acceptance, the PWA creates `RCP-TR027-001`, signs its canonical receipt payload with the device key, stores it in IndexedDB, consumes the nonce locally, and displays “Received offline — checking in when connected.”
6. Reconnection invokes the real Google ADK `reconciliation_agent` and its `reconcile_signed_receipt` tool. Deterministic code checks the device signature, note signature, identity binding, expiry-at-receipt, nonce, and current cloud workflow state.
7. A valid receipt atomically changes Mbale from 60 to 49 packs and Busiu from 1 to 12, records the idempotency key, marks `TR-027` delivered, and appends the hash-chained audit event. The same receipt retry returns an idempotent acknowledgment and applies zero mutations.

## Wire formats

- Note QR: `TULINA1.<base64url(JSON envelope)>`
- Receipt upload: `TULINA_RECEIPT1.<base64url(JSON envelope)>`
- Signature: ECDSA P-256 with SHA-256, IEEE P1363 raw `r || s`, 64 bytes, base64url without padding
- Signed bytes: the UTF-8 canonical payload string preserved in the envelope

The note binds transfer, donor, recipient, product, batch, quantity, approval, issue time, expiry, and nonce. The receipt binds receipt ID, note ID, device ID, receive decision/time, and local sequence. Versioned contracts are in `contracts/v1`.

## Keys

Fixture mode verifies the preserved public keys and signatures in the canonical source pack without changing them. Live local mode generates an issuer key into the ignored runtime SQLite database; no private key is present in source control. Browser device private keys are non-exportable and remain in IndexedDB. GCP mode signs SHA-256 digests with a non-exportable Cloud KMS `EC_SIGN_P256_SHA256` key and converts KMS DER signatures to the same offline Web Crypto-compatible P1363 format.

## Nine acceptance vectors

| Vector | Gate | Expected result | Stock mutations |
|---|---|---|---:|
| TST-01 valid offline receipt | edge + cloud | accepted offline, applied once | 1 |
| TST-02 quantity changed | signature | rejected before receipt | 0 |
| TST-03 same nonce twice | local replay | rejected before receipt | 0 |
| TST-04 wrong facility | recipient binding | rejected before receipt | 0 |
| TST-05 expired note | time | rejected before receipt | 0 |
| TST-06 unknown key | trust bundle | rejected before signature evaluation | 0 |
| TST-07 state changed during outage | reconciliation | quarantined for human review | 0 |
| TST-08 duplicate upload | idempotency | acknowledged, no second write | 0 |
| TST-09 malformed QR | parse | rejected before receipt | 0 |

Backend tests execute all nine canonical vectors. Frontend tests independently verify the preserved P-256 fixture with Web Crypto and exercise the non-exportable device key, IndexedDB queue, signed receipt, and local replay guard.

## Current boundary

The local adapter serializes reconciliation in one process and uses SQLite transactions. Cloud Run multi-instance mode uses Firestore transaction claims/idempotency and Cloud KMS signing. The UI labels every fixture value as synthetic and stores no patient data. The hackathon deployment's role headers remain demo authentication; real operations require verified workforce identity.
