# Domain rules and calculations

Phase 1 deliberately separates calculations from model behavior. The rules below are pure, deterministic, and covered by unit tests.

## Stock position

- Average monthly consumption (AMC) is the arithmetic mean of the four supplied monthly issue records.
- Days of cover = `on hand ÷ AMC × 30`.
- Target quantity = `ceil(AMC × target months)`; target months is 2 in the fixture.
- Safety quantity = `ceil(AMC × safety months)`; safety months is 1.
- Need = `max(0, target quantity − on hand)`.
- Safe release = `max(0, on hand − safety quantity)`.

For `F01/P05`, on hand is 60 and AMC is 12, so safe release is 48. For `F02/P05`, on hand is 1 and AMC is 6, so need is 11. The matched quantity is the minimum of safe release, need, and the selected batch balance: 11.

## Watch and match

The Watch calculation publishes a need below target and an offer only when cover exceeds the configured excess trigger while safety stock remains protected. The Match calculation joins compatible product signals, selects the earliest-expiry available batch (FEFO), finds a route and compatible vehicle, applies policy, and ranks allowed candidates using visible need, expiry, and distance components.

Canonical IDs such as `TR-027` are joined from the baseline `MOBIUS` acceptance records only after the quantity and evidence have been calculated. A test changes the expected-output quantity to 99 and proves the engine still calculates 11.

## Policy gates

Every recommendation must pass exactly five gates:

1. donor cover remains at or above protected safety stock;
2. recipient care level is authorized for the medicine;
3. the FEFO batch is available and contains the proposed quantity;
4. a positive route exists;
5. vehicle capacity and temperature range are compatible.

The configured quantity threshold determines whether a named DHO approval is required. Policy can block a proposal, but software or a model cannot grant that approval.

## Persistence

The local repository uses SQLite transactions and the same behavioral boundaries planned for Firestore. It persists inventory positions, transfer state, a unique idempotency ledger, and SHA-256 hash-chained audit events. Applying `TR-027` twice produces one mutation: donor `60 → 49`, recipient `1 → 12`, then a duplicate acknowledgement with zero additional mutations.
