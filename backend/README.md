# Backend domain workspace

The backend now includes the credential-free domain foundation and Phase 3 agent runtime:

- `tulina/fixtures.py` validates and loads the immutable source pack.
- `tulina/engine.py` calculates stock positions, watch signals, safe matches, and evidence.
- `tulina/policy.py` enforces cover, facility level, batch, route, and transport gates.
- `tulina/state_machine.py` prevents approval or delivery authority from being bypassed.
- `tulina/repository.py` persists inventory, transfers, idempotency keys, and a hash-chained audit log in SQLite.
- `tulina/metrics.py` calculates judge-facing operational results.
- `tulina/agents/fleet.py` defines the real six-agent Google ADK hierarchy.
- `tulina/agents/tools.py` exposes deterministic calculations as validated ADK function tools.
- `tulina/agents/store.py` persists queued runs and the agent/tool timeline in SQLite.
- `tulina/agents/providers.py` selects a faithful fixture explanation or Gemini 3.5 Flash structured output.
- `tulina/agents/queue.py` provides local durable queue and Pub/Sub publisher adapters.

Run `python -m backend.tulina.cli recommend` to inspect derived recommendations. Run `python -m backend.tulina.agents.cli --reset` to execute the ADK fleet from a scheduled event rather than a chat prompt.
