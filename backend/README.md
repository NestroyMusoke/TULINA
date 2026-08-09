# Backend domain workspace

Phase 1 provides the credential-free domain foundation:

- `tulina/fixtures.py` validates and loads the immutable source pack.
- `tulina/engine.py` calculates stock positions, watch signals, safe matches, and evidence.
- `tulina/policy.py` enforces cover, facility level, batch, route, and transport gates.
- `tulina/state_machine.py` prevents approval or delivery authority from being bypassed.
- `tulina/repository.py` persists inventory, transfers, idempotency keys, and a hash-chained audit log in SQLite.
- `tulina/metrics.py` calculates judge-facing operational results.

Run `python -m backend.tulina.cli recommend` to inspect derived recommendations or `scripts\seed.ps1` to create the local database.
