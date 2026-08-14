# Tulina four-minute demo script

Target runtime: 3:50–4:00. Record one continuous product story, then use a short prepared cloud-proof cut without claiming credentials or services that are not visible.

## Before recording

1. Run `scripts\test.ps1` and keep the passing summary available.
2. Deploy and run `infra\gcp\verify.ps1 -ProjectId YOUR_PROJECT_ID`.
3. Open the deployed `/judge` URL, the Cloud Run `tulina-api` service page, and a Cloud Logging query showing `AGENT_RUN_COMPLETED`.
4. Confirm `/api/v1/agent-registry` reports `Google ADK`, provider `gemini`, model `gemini-3.5-flash` or newer, and `gemini_called: true` after a live run.
5. Select **Reset demo**. Use a 1440 × 900 browser for the district story; keep a 390 × 844 device viewport ready for the facility shot.
6. Replace the hosted/video placeholders only after those artifacts exist.

## Timed run

| Time | Screen and action | Narration | Proof to keep visible |
|---|---|---|---|
| 0:00–0:18 | District View hero, then Judge Demo | “One clinic is empty. The district isn’t. Tulina finds safe medicine already nearby, brings in the right human, and proves delivery even without internet.” | Product promise; synthetic-data label |
| 0:18–0:48 | **Read demo card**, expand evidence, **Confirm stock observation** | “A facility worker photographs a stock card. Gemini turns the image into structured stock data with evidence and confidence. This recording uses the live provider; fixture mode is separately labelled and never pretends to call Gemini. A person still confirms the observation.” | Supplied image; confidence/evidence; provider label; human gate |
| 0:48–1:22 | **Next moment**, expand **Technical proof** and **How Tulina decided** | “That inventory event queues a background Google ADK fleet. Watch detects Busiu at five days of cover. Match derives 11 safe packs at Mbale. Steward checks donor cover, expiry order, route, cold chain, and level of care.” | Six agents; run ID; HTTP-backed activity; TR-027 evidence |
| 1:22–1:48 | Advance to approval; show DHO role and approve | “Agents may find and prepare this move, but they cannot approve it. The District Health Officer records APR-DHO-001, and the state machine rejects any attempt to skip that authority.” | Waiting for DHO; human approval record |
| 1:48–2:18 | Issue Tulina Note; show QR and offline state | “Dispatch now asks Cloud KMS to sign one one-use Tulina Note for Busiu’s designated device. The phone cached only public trust before losing signal; no private issuer key or model is on the device.” | CAP-TR027-001; signed QR; DEV-F02-01; unmistakable Offline state |
| 2:18–2:48 | Advance to **Received offline** | “Offline, Web Crypto checks the issuer, recipient, expiry, and nonce. IndexedDB holds a device-signed receipt. This moment makes zero server calls.” | Safe/received state; ‘checking in when connected’; technical check list |
| 2:48–3:20 | Reconnect and advance to **Delivery confirmed** | “On reconnect, Reconciliation verifies both signatures and performs one atomic mutation: Mbale 60 to 49; Busiu 1 to 12. Busiu’s cover rises from five to sixty days.” | Before/after quantities; exactly one mutation; delivery timeline |
| 3:20–3:40 | Advance to replay/tamper proof; open Activity | “Retrying the same receipt applies zero. Changing 11 to 17 after signing is rejected before receipt creation, reported without the signed token, and appended to the verified audit chain.” | Duplicate applied zero; signature invalid; Offline tamper blocked; Chain verified |
| 3:40–3:55 | Cloud Run/Logging prepared tab | “This is the running Cloud Run revision. Firestore holds durable workflows, Pub/Sub delivers background work, Vertex AI serves Gemini, and Cloud KMS keeps the signer key non-exportable.” | `.run.app` URL, revision ready, log trace/run ID, verify-script result |
| 3:55–4:00 | Return to final Tulina screen | “Tulina turns district stock into safe, human-authorized action—online or offline.” | Final impact and audit screen |

## Recording discipline

- Do not say that fixture-mode extraction is a live Gemini call. The provider label must match the run being shown.
- Do not expose API keys, project billing details, access tokens, private keys, receipt tokens, raw prompts, or patient information.
- Keep hidden reasoning out of the video. Show named tools, validated facts, actors, decisions, run/trace IDs, and audit hashes.
- If a moment stalls, stop and reset; do not edit the DOM or replace the product with static screenshots.
- The cloud segment must show a real revision or verified command output. Repository code alone is not cloud-deployment proof.

## Screenshot shot list

1. District hero and **Found nearby** recommendation with `TR-027`.
2. Stock-card image, extracted fields, confidence, evidence, and human confirmation.
3. Six-agent activity with Google ADK run ID and **How Tulina decided**.
4. Facility phone offline with signed Tulina Note and queued receipt.
5. Delivery proof plus duplicate/tamper audit and Cloud Run proof.
