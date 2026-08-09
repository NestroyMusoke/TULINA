# Tulina contracts v1

These JSON Schemas are the language-neutral boundary for facility, inventory, recommendation, and audit records. The Python models enforce the same invariants. Later agent and browser phases must validate untrusted/model-produced records against these contracts before invoking a tool or action.

Contract changes are additive within `v1`; breaking changes require a new directory.
