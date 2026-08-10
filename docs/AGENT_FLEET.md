# Tulina agent fleet

Phase 3 implements a real Google ADK hierarchy that starts from an inventory event or schedule, not a chat prompt. The local demo and Google Cloud modes use the same request and run contracts.

## Runtime flow

```mermaid
sequenceDiagram
    participant UI as District View
    participant API as FastAPI
    participant Q as Local queue / Pub/Sub
    participant ADK as Google ADK Runner
    participant T as Deterministic tools
    participant S as Durable store + audit
    participant G as Gemini 3.5 Flash

    UI->>API: POST watch event
    API->>S: Persist QUEUED run
    API->>Q: Publish run reference
    API-->>UI: 202 + run ID
    Q->>ADK: Process run asynchronously
    loop Six registered agents
        ADK->>T: Invoke validated FunctionTool
        T-->>ADK: Typed result
        ADK->>S: Persist step + audit event
    end
    ADK->>G: Explain validated recommendation (live mode only)
    G-->>ADK: DecisionExplanation schema
    ADK->>S: Complete run; leave approval to DHO
    UI->>API: Poll run status
    API-->>UI: Durable agent/tool timeline
```

## Responsibilities and authority

| ADK agent | Tool | Durable evidence | Authority boundary |
|---|---|---|---|
| `stock_intake_agent` | `validate_inventory_snapshot` | source label, record count, focus stock | Phase 3 validates existing observations; image extraction arrives in Phase 4 |
| `watch_agent` | `detect_stock_signals` | need/offer counts and focus cover | Reads stock; cannot propose a donor alone |
| `match_agent` | `rank_safe_transfers` | ranked candidates and full validated recommendation | Proposes only; cannot approve or mutate |
| `steward_agent` | `evaluate_governance` | five policy gates and concise explanation | Blocks unsafe proposals; cannot grant human authority |
| `dispatch_agent` | `check_dispatch_gate` | ready/waiting state | Cannot issue a note before approval; signing arrives in Phase 5 |
| `reconciliation_agent` | `check_reconciliation_gate` | ready/waiting state | Cannot mutate without a verified receipt; protocol arrives in Phase 5 |

## Asynchronous and persistent behavior

- `POST /api/v1/agent-runs/watch` writes a `QUEUED` run and returns HTTP 202.
- Local mode processes through a FastAPI background task; `POST /api/v1/agent-worker/process-next` can resume the next queued job after a restart.
- Pub/Sub mode publishes only a versioned durable run record. Cloud Run push wiring is delivered in Phase 7.
- SQLite tables `agent_runs` and `agent_steps` retain status, timestamps, tool names, safe evidence, result transfer, and ADK event authors.
- The hash-chained audit log records queue, runtime, agent start/completion, and failure events. Prompts and hidden model reasoning are not stored.

## Provider modes

- `fixture`: no key required. The full ADK fleet and deterministic tools run; explanation output is a faithful saved calculation and the registry reports `gemini_called: false`.
- `gemini`: requires `GOOGLE_API_KEY`; uses `gemini-3.5-flash` by default.
- `gcp`: requires `GOOGLE_CLOUD_PROJECT`; uses Vertex AI with the same model contract.

Startup rejects an unversioned model name, Gemini older than 3.5, missing live credentials, or Pub/Sub mode without a project ID.

## Proof hooks

- `GET /api/v1/agent-registry` — framework version, six registered agents, tools, provider, model, and queue.
- `GET /api/v1/agent-runs/{run_id}` — durable run and tool-step timeline.
- `GET /api/v1/agent-runs/latest` — latest background run for an authorized role.
- `python -m backend.tulina.agents.cli --reset` — non-chat scheduled execution for CI and video evidence.

## Honest Phase 3 limits

Live Gemini calls require credentials and are covered locally by a schema-validation adapter test, not a fabricated network response. Stock-card vision, signed Tulina Notes, Firestore persistence, Cloud Run subscribers, and production retry/quarantine policy remain in their named phases.
