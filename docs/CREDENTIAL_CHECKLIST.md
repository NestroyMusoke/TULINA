# Credential and proof checklist

No credential is required for the complete fixture acceptance demo. The items below are only for live Gemini, Google Cloud deployment, and final Devpost submission.

## Before adding credentials

- [ ] Copy `.env.example` to ignored `.env`; never edit `.env.example` with a real value.
- [ ] Use a dedicated Google Cloud project and billing budget/alerts.
- [ ] Prefer `gcloud auth application-default login` and Cloud Run service identities over downloaded service-account keys.
- [ ] Confirm the selected region offers the required Gemini model and services.
- [ ] Run `python scripts\scan_secrets.py` before every public push.
- [ ] Check `git status --ignored` and `git grep` for `.env`, API keys, access tokens, private PEM material, credentials JSON, raw receipt/note tokens, and screenshots containing console secrets.

## Live Gemini API mode

- [ ] Set `TULINA_MODE=gemini`.
- [ ] Set `GOOGLE_API_KEY` only in `.env` or the process environment.
- [ ] Keep `GEMINI_MODEL=gemini-3.5-flash` or a newer supported model.
- [ ] Confirm the Agent Registry says provider `gemini` and a completed live run says `gemini_called: true`.
- [ ] Remove or rotate the key after recording if it was ever exposed on screen.

## Google Cloud deployment

- [ ] Record the exact `GOOGLE_CLOUD_PROJECT`, region, and Firestore location.
- [ ] Run `gcloud auth login`; use ADC only for the local seed/verification commands that need it.
- [ ] Execute `infra\gcp\deploy.ps1 -ProjectId YOUR_PROJECT_ID`.
- [ ] Capture the emitted web/API `.run.app` URLs.
- [ ] Execute `infra\gcp\verify.ps1 -ProjectId YOUR_PROJECT_ID` and save the successful, non-secret output for the video.
- [ ] Confirm Cloud Run API readiness reports Firestore, Pub/Sub, ADK, Gemini, and `cloud-kms-p256`.
- [ ] Confirm the Pub/Sub push identity and audience match the backend service.
- [ ] Confirm runtime service accounts match `docs/IAM_GCP.md`; do not grant Editor/Owner to them.
- [ ] Confirm the KMS private key is non-exportable and no local production private key exists.
- [ ] Set Cloud Run minimum instances to zero and maximum to three unless the demo needs a temporary warm instance.

## Before recording

- [ ] Open only sanitized browser/console tabs.
- [ ] Hide project numbers, billing details, account emails, bearer tokens, and environment-variable values where they are not needed as proof.
- [ ] Reset the synthetic demo and confirm the provider label matches the narration.
- [ ] Show Cloud Run revision/URL, ADK/Gemini registry, one trace/run ID, Pub/Sub or Firestore proof, and the final audit chain.
- [ ] Never show hidden model reasoning or imply fixture output is a live model call.

## Devpost handoff

- [ ] Confirm Devpost registration and eligibility directly in the authenticated account.
- [ ] Add the hosted URL, public repository URL, architecture image, and final video URL.
- [ ] If the repository is private, grant the two judge addresses stated in the official requirements.
- [ ] Verify the video is approximately four minutes and visibly proves the backend runs on Google Cloud.
- [ ] Replace every `TODO` in `docs/DEVPOST_SUBMISSION.md`.
- [ ] Re-run the release gate and secret scan after the final edit.

## After judging or demo use

- [ ] Use `infra\gcp\teardown.ps1` in dry-run mode first.
- [ ] Execute teardown only with the exact project confirmation.
- [ ] Review retained Firestore/KMS resources deliberately; the script does not destroy them automatically.
- [ ] Revoke temporary principals and rotate exposed API keys.
