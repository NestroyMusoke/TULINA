# Tulina contracts v1

These JSON Schemas are the language-neutral boundary for facility, inventory, recommendation, audit, governance, agent-run, stock-card intake, Tulina Note, offline trust, and reconciliation records. Strict Python and TypeScript models enforce the same invariants. Model-produced records are validated before a tool or action, and agent-run records intentionally exclude prompts and hidden model reasoning.

Contract changes are additive within `v1`; breaking changes require a new directory.
