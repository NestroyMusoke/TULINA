[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z][a-z0-9-]{4,28}[a-z0-9]$')]
    [string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$FirestoreLocation = "us-central1",
    [string]$FirestoreDatabase = "(default)",
    [string]$Namespace = "tulina-demo",
    [string]$GeminiModel = "gemini-3.5-flash"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$gcloud = (Get-Command gcloud.cmd -ErrorAction SilentlyContinue).Source
if (-not $gcloud) { $gcloud = (Get-Command gcloud -ErrorAction SilentlyContinue).Source }
if (-not $gcloud) { throw "Google Cloud CLI was not found. Install it, run gcloud auth login, and retry." }

function Invoke-Gcloud {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $gcloud @Arguments
    if ($LASTEXITCODE -ne 0) { throw "gcloud failed: $($Arguments -join ' ')" }
}

function Test-Gcloud {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $gcloud @Arguments *> $null
    return $LASTEXITCODE -eq 0
}

function Add-ProjectRole {
    param([string]$Member, [string]$Role)
    Invoke-Gcloud projects add-iam-policy-binding $ProjectId "--member=$Member" "--role=$Role" --quiet
}

function Ensure-ServiceAccount {
    param([string]$Name, [string]$DisplayName)
    $email = "$Name@$ProjectId.iam.gserviceaccount.com"
    if (-not (Test-Gcloud iam service-accounts describe $email "--project=$ProjectId")) {
        Invoke-Gcloud iam service-accounts create $Name "--display-name=$DisplayName" "--project=$ProjectId" | Out-Host
    }
    return $email
}

function Ensure-CompositeIndex {
    param([string]$CollectionGroup, [string[]]$Fields)
    $arguments = @(
        "firestore", "indexes", "composite", "create",
        "--project=$ProjectId", "--database=$FirestoreDatabase",
        "--collection-group=$CollectionGroup", "--query-scope=collection", "--async"
    )
    foreach ($field in $Fields) { $arguments += "--field-config=$field" }
    $output = & $gcloud @arguments 2>&1
    if ($LASTEXITCODE -ne 0 -and ($output -join "`n") -notmatch "ALREADY_EXISTS|already exists") {
        throw "Could not create Firestore index for $CollectionGroup`: $($output -join ' ')"
    }
}

function Wait-FirestoreIndexes {
    $required = @(
        "audit_events", "agent_runs", "agent_steps",
        "stock_card_intakes", "reconciliation_results"
    )
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        $raw = & $gcloud firestore indexes composite list "--project=$ProjectId" `
            "--database=$FirestoreDatabase" --format=json
        if ($LASTEXITCODE -ne 0) { throw "Could not inspect Firestore index readiness." }
        $indexes = $raw | ConvertFrom-Json
        $relevant = @($indexes | Where-Object {
            $name = [string]$_.name
            $required | Where-Object { $name -match "/collectionGroups/$([regex]::Escape($_))/indexes/" }
        })
        $groups = @($relevant | ForEach-Object {
            if ([string]$_.name -match "/collectionGroups/([^/]+)/indexes/") { $Matches[1] }
        } | Select-Object -Unique)
        $pending = @($relevant | Where-Object { $_.state -ne "READY" })
        if ($groups.Count -ge $required.Count -and $pending.Count -eq 0) { return }
        Write-Host "Waiting for Firestore indexes ($attempt/60)..."
        Start-Sleep -Seconds 10
    }
    throw "Firestore indexes did not become ready within ten minutes. Inspect them before running the demo."
}

Push-Location $root
try {
    Invoke-Gcloud config set project $ProjectId
    Invoke-Gcloud services enable `
        run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com `
        firestore.googleapis.com pubsub.googleapis.com cloudkms.googleapis.com `
        aiplatform.googleapis.com iamcredentials.googleapis.com "--project=$ProjectId"

    $repositoryName = "tulina"
    if (-not (Test-Gcloud artifacts repositories describe $repositoryName "--location=$Region" "--project=$ProjectId")) {
        Invoke-Gcloud artifacts repositories create $repositoryName `
            "--repository-format=docker" "--location=$Region" `
            "--description=Tulina Cloud Run images" "--project=$ProjectId"
    }

    $backendServiceAccount = Ensure-ServiceAccount "tulina-api" "Tulina API runtime"
    $frontendServiceAccount = Ensure-ServiceAccount "tulina-web" "Tulina web runtime"
    $pushServiceAccount = Ensure-ServiceAccount "tulina-pubsub-push" "Tulina authenticated Pub/Sub push"
    Add-ProjectRole "serviceAccount:$backendServiceAccount" "roles/datastore.user"
    Add-ProjectRole "serviceAccount:$backendServiceAccount" "roles/pubsub.publisher"
    Add-ProjectRole "serviceAccount:$backendServiceAccount" "roles/aiplatform.user"
    Add-ProjectRole "serviceAccount:$backendServiceAccount" "roles/logging.logWriter"
    Add-ProjectRole "serviceAccount:$frontendServiceAccount" "roles/logging.logWriter"

    $projectNumber = (& $gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $projectNumber) { throw "Could not resolve the Google Cloud project number." }
    $pubsubServiceAgent = "service-$projectNumber@gcp-sa-pubsub.iam.gserviceaccount.com"
    Add-ProjectRole "serviceAccount:$pubsubServiceAgent" "roles/iam.serviceAccountTokenCreator"
    Add-ProjectRole "serviceAccount:$pubsubServiceAgent" "roles/pubsub.publisher"
    Add-ProjectRole "serviceAccount:$pubsubServiceAgent" "roles/pubsub.subscriber"

    $buildServiceAccountResource = (& $gcloud builds get-default-service-account "--project=$ProjectId").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $buildServiceAccountResource) { throw "Could not resolve the Cloud Build service account." }
    $buildServiceAccount = ($buildServiceAccountResource -split "/")[-1]
    Add-ProjectRole "serviceAccount:$buildServiceAccount" "roles/artifactregistry.writer"
    Add-ProjectRole "serviceAccount:$buildServiceAccount" "roles/logging.logWriter"

    if (-not (Test-Gcloud firestore databases describe "--database=$FirestoreDatabase" "--project=$ProjectId")) {
        Invoke-Gcloud firestore databases create "--database=$FirestoreDatabase" `
            "--location=$FirestoreLocation" "--type=firestore-native" `
            --delete-protection "--project=$ProjectId"
    }

    Ensure-CompositeIndex "audit_events" @("field-path=trace_id,order=ascending", "field-path=sequence,order=ascending")
    Ensure-CompositeIndex "agent_runs" @("field-path=status,order=ascending", "field-path=created_at,order=ascending")
    Ensure-CompositeIndex "agent_steps" @("field-path=run_id,order=ascending", "field-path=sequence,order=ascending")
    Ensure-CompositeIndex "stock_card_intakes" @("field-path=status,order=ascending", "field-path=created_at,order=descending")
    Ensure-CompositeIndex "reconciliation_results" @("field-path=receipt_id,order=ascending", "field-path=sequence,order=descending")
    Ensure-CompositeIndex "reconciliation_results" @("field-path=decision,order=ascending", "field-path=sequence,order=descending")
    Wait-FirestoreIndexes

    $keyRing = "tulina"
    $keyName = "tulina-note"
    if (-not (Test-Gcloud kms keyrings describe $keyRing "--location=$Region" "--project=$ProjectId")) {
        Invoke-Gcloud kms keyrings create $keyRing "--location=$Region" "--project=$ProjectId"
    }
    if (-not (Test-Gcloud kms keys describe $keyName "--keyring=$keyRing" "--location=$Region" "--project=$ProjectId")) {
        Invoke-Gcloud kms keys create $keyName "--keyring=$keyRing" "--location=$Region" `
            --purpose=asymmetric-signing --default-algorithm=ec-sign-p256-sha256 `
            --protection-level=software "--project=$ProjectId"
    }
    Invoke-Gcloud kms keys add-iam-policy-binding $keyName "--keyring=$keyRing" `
        "--location=$Region" "--member=serviceAccount:$backendServiceAccount" `
        --role=roles/cloudkms.signerVerifier "--project=$ProjectId" --quiet
    $kmsKeyVersion = (& $gcloud kms keys versions list "--key=$keyName" "--keyring=$keyRing" `
        "--location=$Region" "--project=$ProjectId" --filter="state=ENABLED" `
        --sort-by="~name" --limit=1 --format="value(name)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $kmsKeyVersion) { throw "No enabled Tulina KMS signing key version exists." }

    foreach ($topic in @("tulina-workflows", "tulina-workflows-dead-letter")) {
        if (-not (Test-Gcloud pubsub topics describe $topic "--project=$ProjectId")) {
            Invoke-Gcloud pubsub topics create $topic "--project=$ProjectId"
        }
    }

    $tag = Get-Date -Format "yyyyMMddHHmmss"
    $registry = "$Region-docker.pkg.dev/$ProjectId/$repositoryName"
    $backendImage = "$registry/api:$tag"
    $frontendImage = "$registry/web:$tag"
    Invoke-Gcloud builds submit . --config=infra/gcp/cloudbuild-backend.yaml `
        "--substitutions=_IMAGE=$backendImage" "--project=$ProjectId"

    $fixtureEnvironment = "TULINA_MODE=fixture,TULINA_REPOSITORY=local,TULINA_QUEUE=local,TULINA_DATABASE_PATH=/tmp/tulina.sqlite3"
    Invoke-Gcloud run deploy tulina-api "--image=$backendImage" "--region=$Region" `
        "--service-account=$backendServiceAccount" --allow-unauthenticated `
        --port=8080 --cpu=1 --memory=1Gi --concurrency=20 --timeout=900 `
        --min=0 --max=3 "--set-env-vars=$fixtureEnvironment" `
        "--startup-probe=httpGet.path=/healthz,httpGet.port=8080,failureThreshold=12,timeoutSeconds=2,periodSeconds=5" `
        "--liveness-probe=httpGet.path=/healthz,httpGet.port=8080,initialDelaySeconds=10,failureThreshold=3,timeoutSeconds=2,periodSeconds=30" `
        "--project=$ProjectId"
    $backendUrl = (& $gcloud run services describe tulina-api "--region=$Region" `
        "--project=$ProjectId" --format="value(status.url)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $backendUrl) { throw "Could not resolve the Tulina API URL." }

    $cloudEnvironment = @(
        "TULINA_MODE=gcp", "TULINA_REPOSITORY=firestore", "TULINA_QUEUE=pubsub",
        "GOOGLE_GENAI_USE_VERTEXAI=true", "GOOGLE_CLOUD_PROJECT=$ProjectId",
        "GOOGLE_CLOUD_LOCATION=$Region", "GEMINI_MODEL=$GeminiModel",
        "TULINA_GCP_PROJECT=$ProjectId", "TULINA_PUBSUB_TOPIC=tulina-workflows",
        "TULINA_PUBSUB_AUDIENCE=$backendUrl", "TULINA_PUBSUB_SERVICE_ACCOUNT=$pushServiceAccount",
        "TULINA_FIRESTORE_DATABASE=$FirestoreDatabase", "TULINA_FIRESTORE_NAMESPACE=$Namespace",
        "TULINA_KMS_KEY_VERSION=$kmsKeyVersion",
        "TULINA_ALLOWED_ORIGINS=$backendUrl", "TULINA_AGENT_STEP_DELAY_MS=0"
    ) -join ","
    Invoke-Gcloud run deploy tulina-api "--image=$backendImage" "--region=$Region" `
        "--service-account=$backendServiceAccount" --allow-unauthenticated `
        --port=8080 --cpu=1 --memory=1Gi --concurrency=20 --timeout=900 `
        --min=0 --max=3 "--set-env-vars=$cloudEnvironment" `
        "--startup-probe=httpGet.path=/healthz,httpGet.port=8080,failureThreshold=24,timeoutSeconds=3,periodSeconds=5" `
        "--liveness-probe=httpGet.path=/healthz,httpGet.port=8080,initialDelaySeconds=20,failureThreshold=3,timeoutSeconds=3,periodSeconds=30" `
        "--project=$ProjectId"

    Invoke-Gcloud builds submit . --config=infra/gcp/cloudbuild-frontend.yaml `
        "--substitutions=_IMAGE=$frontendImage,_VITE_API_URL=$backendUrl" "--project=$ProjectId"
    Invoke-Gcloud run deploy tulina-web "--image=$frontendImage" "--region=$Region" `
        "--service-account=$frontendServiceAccount" --allow-unauthenticated `
        --port=8080 --cpu=1 --memory=256Mi --concurrency=80 --timeout=60 `
        --min=0 --max=3 `
        "--startup-probe=httpGet.path=/healthz,httpGet.port=8080,failureThreshold=12,timeoutSeconds=2,periodSeconds=5" `
        "--liveness-probe=httpGet.path=/healthz,httpGet.port=8080,initialDelaySeconds=10,failureThreshold=3,timeoutSeconds=2,periodSeconds=30" `
        "--project=$ProjectId"
    $frontendUrl = (& $gcloud run services describe tulina-web "--region=$Region" `
        "--project=$ProjectId" --format="value(status.url)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $frontendUrl) { throw "Could not resolve the Tulina web URL." }
    Invoke-Gcloud run services update tulina-api "--region=$Region" "--project=$ProjectId" `
        "--update-env-vars=TULINA_ALLOWED_ORIGINS=$frontendUrl"

    Invoke-Gcloud run services add-iam-policy-binding tulina-api "--region=$Region" `
        "--member=serviceAccount:$pushServiceAccount" --role=roles/run.invoker `
        "--project=$ProjectId" --quiet
    $subscription = "tulina-agent-worker"
    if (-not (Test-Gcloud pubsub subscriptions describe $subscription "--project=$ProjectId")) {
        Invoke-Gcloud pubsub subscriptions create $subscription --topic=tulina-workflows `
            "--push-endpoint=$backendUrl/api/v1/internal/pubsub/agent-runs" `
            "--push-auth-service-account=$pushServiceAccount" `
            "--push-auth-token-audience=$backendUrl" `
            --dead-letter-topic=tulina-workflows-dead-letter --max-delivery-attempts=5 `
            --min-retry-delay=10s --max-retry-delay=300s --ack-deadline=600 `
            "--project=$ProjectId"
    }

    Write-Host "Tulina deployed."
    Write-Host "Web: $frontendUrl/judge"
    Write-Host "API: $backendUrl"
    Write-Host "Run infra\gcp\verify.ps1 -ProjectId $ProjectId -Region $Region"
    Write-Warning "Firestore rules are supplied in infra/gcp/firestore.rules. Deploy them with the Firebase CLI if browser SDK access is ever enabled; the current server client is governed by IAM."
} finally {
    Pop-Location
}
