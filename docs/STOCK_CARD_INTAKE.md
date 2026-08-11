# Stock-card intake

Phase 4 turns a camera/file image into a provisional stock observation. It is an action workflow, not a chat surface.

## Runtime flow

1. A facility worker uploads a PNG/JPEG of at most 8 MB or selects the supplied demo card.
2. FastAPI verifies the file signature and passes invocation-scoped image bytes to the ADK `stock_intake_agent`.
3. The agent invokes `extract_stock_card`, which selects the fixture or Gemini multimodal provider.
4. Pydantic validates the full header, four-or-more movement records, current balance, batch, expiry, storage, evidence regions, and confidence.
5. Deterministic code resolves facility, product, and batch IDs and checks final-balance, expiry, storage, evidence, and confidence invariants.
6. Uncertain records become `NEEDS_REVIEW`; corrections preserve previous and corrected values in the durable record and audit chain.
7. A facility worker confirms the observation. Only an `ACCEPTED` record can trigger an inventory-event watch cycle.

Raw image bytes are never written to SQLite. The durable record contains the source filename, MIME type, byte count, SHA-256, structured facts, evidence, corrections, provider/model proof, and timestamps.

## Providers

- `fixture`: verifies `stock_card_scan_demo.png` against `data/fixtures/manifest.json`, then loads `stock_card_extraction_v1.json`. Any other image fails with an actionable message. `gemini_called` is false.
- `gemini`: sends the image and injection-resistant extraction instruction to Gemini 3.5 Flash or newer using structured output. `gemini_called` is true. Invalid output fails closed.

Live Gemini is credential-gated and is tested locally with a mocked SDK boundary; the project does not claim that a live model call occurred during credential-free tests.

## API proof hooks

- `GET /api/v1/demo/stock-card-image`
- `POST /api/v1/demo/stock-card-intakes`
- `POST /api/v1/stock-card-intakes` (multipart `file`)
- `GET /api/v1/stock-card-intakes/latest`
- `GET /api/v1/stock-card-intakes/{intake_id}`
- `PATCH /api/v1/stock-card-intakes/{intake_id}`
- `POST /api/v1/stock-card-intakes/{intake_id}/accept`

Upload, correction, and acceptance require the server-enforced `facility_worker` role. DHO and auditor roles can inspect records but cannot alter facility observations.
