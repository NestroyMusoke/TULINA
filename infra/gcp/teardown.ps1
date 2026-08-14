[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [switch]$Execute,
    [string]$ConfirmProjectId
)

$ErrorActionPreference = "Stop"
$commands = @(
    @("run", "services", "delete", "tulina-web", "--region=$Region", "--project=$ProjectId", "--quiet"),
    @("run", "services", "delete", "tulina-api", "--region=$Region", "--project=$ProjectId", "--quiet"),
    @("pubsub", "subscriptions", "delete", "tulina-agent-worker", "--project=$ProjectId", "--quiet"),
    @("pubsub", "topics", "delete", "tulina-workflows", "--project=$ProjectId", "--quiet"),
    @("pubsub", "topics", "delete", "tulina-workflows-dead-letter", "--project=$ProjectId", "--quiet"),
    @("artifacts", "repositories", "delete", "tulina", "--location=$Region", "--project=$ProjectId", "--quiet")
)

if (-not $Execute) {
    Write-Host "Dry run only. The following billable stateless resources would be removed:"
    foreach ($command in $commands) { Write-Host "gcloud $($command -join ' ')" }
    Write-Host "Firestore and KMS are deliberately retained to preserve audit evidence and signing trust."
    Write-Host "To execute, rerun with -Execute -ConfirmProjectId $ProjectId"
    exit 0
}
if ($ConfirmProjectId -ne $ProjectId) {
    throw "Teardown requires -ConfirmProjectId with the exact project ID."
}
$gcloud = (Get-Command gcloud.cmd -ErrorAction SilentlyContinue).Source
if (-not $gcloud) { $gcloud = (Get-Command gcloud -ErrorAction SilentlyContinue).Source }
if (-not $gcloud) { throw "Google Cloud CLI was not found." }
$activeProject = (& $gcloud config get-value project 2>$null).Trim()
if ($activeProject -ne $ProjectId) {
    throw "Active gcloud project '$activeProject' does not match confirmed target '$ProjectId'."
}
foreach ($command in $commands) {
    & $gcloud @command
    if ($LASTEXITCODE -ne 0) { Write-Warning "Resource was absent or could not be removed: gcloud $($command -join ' ')" }
}
Write-Host "Stateless Tulina resources removed. Firestore and KMS remain recoverable in project $ProjectId."
