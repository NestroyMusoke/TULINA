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

## Current Phase 4 rehearsal

The Judge Demo now starts with the supplied synthetic stock-card image. **Read demo card** invokes the real ADK Stock Intake Agent and validated extraction tool, then displays four movement rows, the 60-pack balance, early batch, expiry, cold-chain evidence, field confidence, and the provider proof. A facility worker explicitly confirms the observation; only then can the next moment publish the inventory event and run the six-agent district workflow. Reset removes both intake and agent runs before reseeding the canonical fixture. Signing, offline receipt, and reconciliation extend this route in Phase 5.
