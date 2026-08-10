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

## Current Phase 2 rehearsal

The implemented Judge Demo covers the first operational arc in four real moments: district picture, background discovery, approval request, and human approval. Reset reseeds the canonical fixture and appends a reset event; each Next Moment button invokes the corresponding server operation. The stock-card, signed note, offline receipt, and reconciliation moments will extend this same route in Phases 4 and 5.
