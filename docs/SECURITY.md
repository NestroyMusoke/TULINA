# Security and threat model

## Boundaries

- Server-side demo roles are explicit: facility worker, DHO approver, auditor.
- Gemini may extract, clarify, summarize, or plan agent work. It cannot approve, sign, or mutate inventory.
- Tool inputs and model outputs are schema-validated; untrusted stock-card text is data, never instructions.
- A Tulina Note is signed with ECDSA P-256/SHA-256 and binds issuer key, recipient facility, transfer, batch, quantity, approval, nonce, and expiry. Its signed receipt binds the designated device identity.
- Offline devices cache issuer public keys only. Production issuer private keys stay in Cloud KMS; local development generates one into the ignored runtime database. Device private keys are non-exportable Web Crypto keys in IndexedDB.
- Reconciliation checks signature, key, recipient, expiry, nonce, workflow state, and idempotency in one transaction.

## Threats handled

Tampered quantity, replayed nonce, wrong facility, expired authorization, unknown issuer, malformed payload, duplicate upload, cloud/edge conflict, prompt injection, tool-output poisoning, privilege escalation, leaked secrets, and partial queue failure. Conflicts are quarantined for human review; no silent merge occurs.

Audit records form a SHA-256 hash chain and contain concise evidence/tool events—not hidden model reasoning or patient data.
