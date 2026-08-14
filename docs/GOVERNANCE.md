# Human authority and audit governance

## Decision chain

1. Stock Intake creates a provisional observation; a facility worker confirms it.
2. Watch and Match calculate a proposal from validated stock, consumption, expiry, route, and transport records.
3. Steward evaluates deterministic policy gates and requests human authority.
4. The named DHO approves `APR-DHO-001` or does nothing. Gemini and ADK cannot substitute for this step.
5. Dispatch verifies the approved state and issues a signed, one-use Tulina Note.
6. Reconciliation verifies the device receipt and either applies one mutation, returns an idempotent acknowledgement, rejects it, or quarantines a cloud-state conflict.

## Evidence policy

Primary UI copy stays human: **Found nearby**, **Safe to receive**, **Delivery confirmed**, and **Needs human review**. Expandable decision and audit views may show validated policy gates, confidence, tool names, actors, traces, event hashes, provider/model proof, and before/after stock. They must not show or claim hidden model reasoning.

Audit events are ordered, previous-hash linked, and recomputed by the server. Human-readable summaries never replace the underlying deterministic evidence. Secrets and raw untrusted inputs are removed before hashing.

## Exception governance

Cloud/edge disagreement is never silently merged. The receipt is quarantined with zero mutation and remains visible to a DHO and auditor. Only the DHO may record `ACKNOWLEDGE_NO_MUTATION`; the auditor is read-only. Repeating the same resolution request is idempotent and creates no second governance event.

Acknowledgement closes the review record but does not deliver, cancel, or invent stock. Any follow-up action requires a new workflow under the normal policy and approval rules.
