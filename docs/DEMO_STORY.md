# Canonical judge demo

The deterministic four-minute path uses `TR-027`: Mbale Regional Referral Hospital (`F01`) can safely send 11 packs of Oxytocin 10 IU/ml (`P05`, batch `BAT-F01-P05-01` / `OXY-MBL-2610A`) to Busiu Health Centre IV (`F02`). The DHO approves as `APR-DHO-001`.

1. Upload the supplied stock-card photo and show extracted fields, confidence, and visual evidence.
2. Start the background watch. Activity appears without a chat prompt.
3. Open **Found nearby** and expand **How Tulina decided**.
4. Approve as DHO; issue the signed one-use `CAP-TR027-001` shown as a Tulina Note.
5. Switch the `DEV-F02-01` facility phone offline, scan, verify the cached public trust bundle, and queue the receipt in IndexedDB.
6. Reconnect. Reconciliation applies one mutation and both screens show **Delivery confirmed**.
7. Retry the receipt: zero mutations. Run tamper: rejection is visible and audited.
8. Finish on before/after stock, restored cover, avoided expiry, and immutable timeline.

Every moment invokes an API or offline protocol operation. “Next moment” never replaces content with a static screenshot.

## Submission rehearsal

The Judge Demo runs all eight moments with real operations. After the six-agent district watch and DHO approval, the ADK Dispatch Agent issues the signed QR note and the phone caches trust. The network toggle then forces the facility view offline; Web Crypto verifies the note and IndexedDB queues a device-signed receipt with zero API calls. Reconnection invokes the ADK Reconciliation Agent, applies one mutation, and shows before/after stock. The final moment retries the same receipt for zero additional writes, changes the signed quantity to prove rejection, and reports an allowlisted rejection event without sending the signed note. Reset clears intake, runs, protocol state, browser keys, nonce memory, and receipts before reseeding the canonical fixture.

`frontend/e2e/tulina-demo.spec.ts` rehearses this path against the real API and browser. `scripts/capture_submission.ps1` saves the product screenshot set; the owner separately captures credentialed Cloud Run/Gemini proof.
