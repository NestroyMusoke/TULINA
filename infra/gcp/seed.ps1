[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$FirestoreDatabase = "(default)",
    [string]$Namespace = "tulina-demo",
    [switch]$Reset,
    [string]$ConfirmNamespace
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$python = if (Test-Path $bundledPython) { $bundledPython } elseif ($pythonCommand) { $pythonCommand.Source } else { $null }
if (-not $python) { throw "Python 3.12 was not found." }
if ($Reset -and $ConfirmNamespace -ne $Namespace) {
    throw "Reset requires -ConfirmNamespace with the exact namespace value."
}

$arguments = @(
    "-m", "backend.tulina.cloud.cli", "seed",
    "--project", $ProjectId, "--database", $FirestoreDatabase, "--namespace", $Namespace
)
if ($Reset) { $arguments += @("--reset", "--confirm-namespace", $ConfirmNamespace) }
Push-Location $root
try {
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Firestore seed failed. Confirm ADC and roles/datastore.user." }
} finally {
    Pop-Location
}
