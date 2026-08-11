# Backend domain workspace

The backend now includes the credential-free domain foundation, agent runtime, and multimodal stock intake:

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
- `tulina/intake/agent.py` runs the Stock Intake Agent and its extraction tool through a real ADK Runner.
- `tulina/intake/providers.py` selects a SHA-256-bound saved extraction or Gemini vision.
- `tulina/intake/service.py` validates identities, evidence, confidence, corrections, upload type, and human acceptance.
- `tulina/intake/store.py` durably stores structured observations and corrections without retaining image bytes.

Run `python -m backend.tulina.cli recommend` to inspect derived recommendations. Run `python -m backend.tulina.agents.cli --reset` to execute the ADK fleet from a scheduled event rather than a chat prompt.
