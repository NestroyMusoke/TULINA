# Cost control and teardown

The deployment caps both Cloud Run services at three instances and sets minimum instances to zero. Artifact Registry receives one timestamped image per service per deployment. Firestore, Pub/Sub, Vertex AI/Gemini, Cloud Build, Cloud Logging, Artifact Registry, and Cloud KMS may incur Google Cloud charges; quotas and free-tier availability vary by account and region.

Recommended controls:

1. Set a Cloud Billing budget and alerts before deployment.
2. Keep the `--max=3` and `--min=0` Cloud Run limits unless load testing has a documented need.
3. Reuse the existing Firestore database, topics, key, and service accounts; the deployment script is idempotent.
4. Delete old unreferenced Artifact Registry image versions after the video is accepted.
5. Keep Cloud Logging retention proportionate and never log request bodies.
6. Use fixture mode for rehearsal; reserve Gemini/Vertex calls for the cloud proof and final recording.

Preview the stateless teardown from CMD:

```cmd
cd /d "C:\Users\X1 Yoga\Documents\Codex\2026-08-09\tulina"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\infra\gcp\teardown.ps1" -ProjectId "YOUR_PROJECT_ID"
```

The default is a dry run. To remove Cloud Run services, the Pub/Sub subscription/topics, and the Artifact Registry repository:

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\infra\gcp\teardown.ps1" -ProjectId "YOUR_PROJECT_ID" -Execute -ConfirmProjectId "YOUR_PROJECT_ID"
```

Firestore and KMS are deliberately retained: Firestore contains the audit record, and KMS public trust may be needed to verify already-issued notes. The script never deletes the project, database, KMS key, IAM identities, or billing account. Review those durable resources manually only after exporting evidence and deciding that offline notes no longer need verification.

Official references: [Cloud Run minimum instances](https://cloud.google.com/run/docs/configuring/min-instances), [Cloud Run maximum instances](https://cloud.google.com/run/docs/configuring/max-instances), [Google Cloud budgets](https://cloud.google.com/billing/docs/how-to/budgets), and [Cloud KMS pricing](https://cloud.google.com/kms/pricing).
