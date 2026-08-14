# Google Cloud IAM

Tulina uses separate runtime identities. No downloadable service-account key is created or expected.

| Identity | Granted role | Reason |
|---|---|---|
| `tulina-api@PROJECT.iam.gserviceaccount.com` | `roles/datastore.user` | read/write only application Firestore data |
| API identity | `roles/pubsub.publisher` | publish durable agent-run references |
| API identity | `roles/aiplatform.user` | call the configured Gemini model through Vertex AI |
| API identity | `roles/logging.logWriter` | emit structured operational logs |
| API identity, on one KMS key | `roles/cloudkms.signerVerifier` | retrieve public key and sign Tulina Notes; cannot export key material |
| `tulina-web@PROJECT.iam.gserviceaccount.com` | `roles/logging.logWriter` | serve static PWA and health output only |
| `tulina-pubsub-push@PROJECT.iam.gserviceaccount.com` | `roles/run.invoker` on `tulina-api` | invoke the worker route |
| Pub/Sub service agent | `roles/iam.serviceAccountTokenCreator` | mint the configured OIDC push token |
| Pub/Sub service agent | Pub/Sub publisher/subscriber roles | dead-letter forwarding and subscription delivery |
| Cloud Build default identity | Artifact Registry writer and log writer | build/push the two deployable images |

The API is publicly reachable because this hackathon build uses explicit demo-role headers in the PWA. Those headers enforce the server permission matrix but are not proof of workforce identity. Pub/Sub is separately protected at the application route with OIDC audience, verified email, and durable-payload matching. Before real medicine operations, put the API behind an authenticated workforce gateway or IAP and derive roles from verified organization claims; do not treat `X-Tulina-Role` as production authentication.

Firestore browser access is denied. The privileged server client is controlled by IAM, as documented by [Google Cloud](https://cloud.google.com/firestore/docs/reference/libraries). Cloud Run uses its attached service identity for API calls; see [service identity](https://cloud.google.com/run/docs/securing/service-identity).
