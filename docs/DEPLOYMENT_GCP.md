# Google Cloud deployment

Phase 7 deploys two non-root containers to Cloud Run, stores operational state in Firestore, delivers asynchronous ADK runs through authenticated Pub/Sub push, calls Gemini through Vertex AI, and signs Tulina Notes with a non-exportable Cloud KMS P-256 key. Fixture mode remains the no-credential local path.

## What the deployment creates

- `tulina-api` and `tulina-web` Cloud Run services, both scaled to zero when idle and capped at three instances.
- `tulina` Artifact Registry Docker repository and timestamped API/web images.
- a delete-protected Firestore Native `(default)` database, required composite indexes, and the `tulina-demo` environment namespace.
- `tulina-workflows` and `tulina-workflows-dead-letter` topics plus the authenticated `tulina-agent-worker` push subscription.
- separate API, web, and Pub/Sub push service accounts.
- a Cloud KMS `EC_SIGN_P256_SHA256` key version used only by the API service identity.

The script never creates or deletes a project, never stores a service-account key, and never writes a private signing key. The API uses Application Default Credentials supplied by Cloud Run.

## Prerequisites

1. A Google Cloud project with billing enabled.
2. Current Google Cloud CLI, Docker/Cloud Build access, and permission to enable APIs, create service accounts, bind IAM roles, create Firestore, and deploy Cloud Run. For a personal hackathon project, Project Owner is the simplest bootstrap identity; the runtime identities remain least privilege.
3. Authenticate and select the account:

```cmd
cd /d "C:\Users\X1 Yoga\Documents\Codex\2026-08-09\tulina"
gcloud auth login
gcloud auth application-default login
```

The second command is needed only for running the optional seed CLI from the local machine.

## One-command deployment from CMD

Replace `YOUR_PROJECT_ID` with the exact Google Cloud project ID:

```cmd
cd /d "C:\Users\X1 Yoga\Documents\Codex\2026-08-09\tulina"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\infra\gcp\deploy.ps1" -ProjectId "YOUR_PROJECT_ID"
```

The script is idempotent: it describes a resource before creating it and tolerates indexes that already exist. It first performs a fixture-mode API deployment to discover the service URL, then deploys the final GCP revision with Firestore, Pub/Sub, Vertex AI/Gemini, and KMS settings. No key is pasted into an environment variable.

To choose another supported region or namespace:

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\infra\gcp\deploy.ps1" -ProjectId "YOUR_PROJECT_ID" -Region "us-central1" -FirestoreLocation "us-central1" -Namespace "tulina-demo"
```

The repository defaults to `gemini-3.5-flash` and rejects an older model at startup. Model and region availability must be confirmed in the selected project before changing either value.

## Verification and proof hooks

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\infra\gcp\verify.ps1" -ProjectId "YOUR_PROJECT_ID"
```

This read-only command proves both Cloud Run revisions are ready, Firestore is reachable, Pub/Sub exists, the active framework is Google ADK, the active provider is Gemini, and the signer is Cloud KMS. It prints the `/judge` URL and a Cloud Logging query suitable for the demo video.

Additional judge-visible checks:

```cmd
gcloud run services describe tulina-api --region us-central1 --project YOUR_PROJECT_ID
gcloud pubsub subscriptions describe tulina-agent-worker --project YOUR_PROJECT_ID
gcloud firestore databases describe --database="(default)" --project YOUR_PROJECT_ID
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=tulina-api" --project YOUR_PROJECT_ID --limit 20 --format=json
```

## Explicit seed command

The API seeds missing canonical synthetic records idempotently at startup. The local ADC command is available for controlled recovery:

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\infra\gcp\seed.ps1" -ProjectId "YOUR_PROJECT_ID"
```

A reset deletes only the named Tulina namespace and requires a second exact confirmation:

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\infra\gcp\seed.ps1" -ProjectId "YOUR_PROJECT_ID" -Reset -ConfirmNamespace "tulina-demo"
```

## Firestore rules

The browser never connects to Firestore. The server client bypasses Firestore Security Rules and is governed by IAM, so `infra/gcp/firestore.rules` denies every direct web/mobile read and write. The deployment script creates indexes through `gcloud`. If Firebase tooling is already part of the project, publish the deny-all rules explicitly with:

```cmd
npx firebase-tools deploy --only firestore:rules --config infra/gcp/firebase.json --project YOUR_PROJECT_ID
```

Official references: [Cloud Run container deployment](https://cloud.google.com/run/docs/deploying), [Cloud Run health checks](https://cloud.google.com/run/docs/configuring/healthchecks), [authenticated Pub/Sub push](https://cloud.google.com/pubsub/docs/authenticate-push-subscriptions), [Firestore transactions](https://cloud.google.com/firestore/docs/manage-data/transactions), [Firestore server-client security](https://cloud.google.com/firestore/docs/security/rules-fields), and [Cloud KMS asymmetric signatures](https://cloud.google.com/kms/docs/create-validate-signatures).

## Local container verification

Start Docker Desktop, then run:

```cmd
docker build --file Dockerfile --tag tulina-api:phase7 .
docker build --file frontend/Dockerfile --build-arg VITE_API_URL=https://api.example.invalid --tag tulina-web:phase7 .
```

CI executes both exact builds. Cloud Build uses `infra/gcp/cloudbuild-backend.yaml` and `infra/gcp/cloudbuild-frontend.yaml`.
