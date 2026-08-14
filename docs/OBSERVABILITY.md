# Observability and recovery

Phase 6 makes every HTTP operation and business workflow traceable without logging request bodies.

## Correlation

- A valid `X-Request-ID` (8–64 allowlisted characters) is preserved; an invalid or missing value is replaced with `REQ-…`.
- Every request receives a server-owned `TRACE-HTTP-…` identifier.
- Both values return as `X-Request-ID` and `X-Trace-ID` response headers.
- Business audit events created during the request include `request_id` and `request_trace_id` before the event hash is calculated.
- ADK runs retain their separate durable `TRACE-AGENT-…` workflow identity, so request and long-running workflow traces remain distinguishable.

## Structured log event

Each request emits one JSON object to stdout for Cloud Run / Cloud Logging ingestion:

```json
{"timestamp":"2026-08-15T14:12:00Z","severity":"INFO","service":"tulina-api","event":"HTTP_REQUEST_COMPLETED","request_id":"REQ-…","trace_id":"TRACE-HTTP-…","method":"POST","path":"/api/v1/receipts/reconcile","status_code":200,"duration_ms":41.7,"role":"facility_worker"}
```

The logger records method and path but not query values, headers, request/response bodies, stock-card bytes, QR values, receipts, prompts, signatures, keys, or hidden reasoning.

## Probes and proof hooks

- `GET /healthz` — process liveness and configured mode.
- `GET /readyz` — audit-chain verification, repository/provider/queue/signer adapters, and fixture record count.
- `GET /api/v1/governance/status` — DHO/auditor view of chain head, event count, exception count, permission matrix, and reasoning policy.
- `GET /api/v1/audit/events?trace_id=…&limit=…` — bounded hash-chained evidence export.
- `GET /api/v1/agent-runs/{run_id}` — durable ADK run and validated tool-step timeline.
- `GET /api/v1/exceptions` — quarantined reconciliation conflicts and human resolution status.

The Audit view recomputes server evidence through the overview response; it does not display a hard-coded “verified” claim.

## Recovery matrix

| Failure | Persistent evidence | Safe recovery |
|---|---|---|
| Agent/tool step fails | run `FAILED`, step error code, audit event | correct input/configuration; start a new idempotent run |
| Pub/Sub/local delivery repeats | durable run state and receipt idempotency | acknowledge repeat; do not reapply stock |
| Receipt sync loses network | browser IndexedDB remains pending | reconnect or retry; same receipt applies at most once |
| Receipt conflicts with cloud state | quarantined case and audit event | DHO investigates and may acknowledge with `ACKNOWLEDGE_NO_MUTATION` |
| Audit verification fails | readiness false and failed chain status | stop operational writes, preserve database, investigate from last trusted export |
| Gemini unavailable/invalid | no action; provider error at guarded boundary | correct credentials/provider; fixture mode remains available for synthetic demo |

Acknowledging a quarantine never retries or mutates inventory. A future corrective medicine move must begin as a new governed transfer.

Phase 7 configures Cloud Run startup/liveness probes on `/healthz`; the deployment verifier separately requires `/readyz` to prove Firestore reachability and chain integrity. `infra/gcp/verify.ps1` also prints the active Google ADK/Gemini registry and a bounded Cloud Logging query for video evidence.

Phase 8 browser proof connects the human story to the same evidence: the final Activity view must show `DUPLICATE_RECEIPT_RETRY` and `OFFLINE_NOTE_REJECTED` while the server-recomputed audit chain remains valid. Playwright failure traces/screenshots are local ignored artifacts and must be reviewed before sharing.
