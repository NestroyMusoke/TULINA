[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$FirestoreDatabase = "(default)"
)

$ErrorActionPreference = "Stop"
$gcloud = (Get-Command gcloud.cmd -ErrorAction SilentlyContinue).Source
if (-not $gcloud) { $gcloud = (Get-Command gcloud -ErrorAction SilentlyContinue).Source }
if (-not $gcloud) { throw "Google Cloud CLI was not found." }

function Invoke-Gcloud {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $gcloud @Arguments
    if ($LASTEXITCODE -ne 0) { throw "gcloud verification failed: $($Arguments -join ' ')" }
}

$backendUrl = (& $gcloud run services describe tulina-api "--region=$Region" `
    "--project=$ProjectId" --format="value(status.url)").Trim()
$frontendUrl = (& $gcloud run services describe tulina-web "--region=$Region" `
    "--project=$ProjectId" --format="value(status.url)").Trim()
if (-not $backendUrl -or -not $frontendUrl) { throw "Cloud Run service URLs could not be resolved." }

$apiHealth = Invoke-RestMethod "$backendUrl/healthz"
$apiReady = Invoke-RestMethod "$backendUrl/readyz"
$webHealth = Invoke-RestMethod "$frontendUrl/healthz"
$registry = Invoke-RestMethod "$backendUrl/api/v1/agent-registry"
if ($apiHealth.status -ne "ok" -or -not $apiReady.ready) { throw "The API health or readiness proof failed." }
if ($webHealth.status -ne "ok") { throw "The web health proof failed." }
if ($registry.framework -ne "Google ADK" -or $registry.active_provider -ne "gemini") {
    throw "The deployed agent registry is not proving Google ADK with Gemini."
}

Invoke-Gcloud firestore databases describe "--database=$FirestoreDatabase" "--project=$ProjectId"
Invoke-Gcloud pubsub topics describe tulina-workflows "--project=$ProjectId"
Invoke-Gcloud pubsub subscriptions describe tulina-agent-worker "--project=$ProjectId"
Invoke-Gcloud run services describe tulina-api "--region=$Region" "--project=$ProjectId" `
    --format="table(status.url,status.latestReadyRevisionName,spec.template.spec.serviceAccountName)"

Write-Host "Verified Cloud Run web: $frontendUrl/judge"
Write-Host "Verified Cloud Run API: $backendUrl"
Write-Host "ADK: $($registry.framework) $($registry.framework_version)"
Write-Host "Gemini model: $($registry.configured_model)"
Write-Host "Firestore readiness: $($apiReady.database), reachable=$($apiReady.storage_reachable)"
Write-Host "Pub/Sub queue: $($apiReady.queue_backend)"
Write-Host "Signer: $($apiReady.offline_note_signer)"
Write-Host "For video proof: gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=tulina-api' --project=$ProjectId --limit=20 --format=json"
