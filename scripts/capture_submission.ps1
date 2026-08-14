param([string]$BrowserChannel = "chrome")

$ErrorActionPreference = "Stop"
$env:TULINA_CAPTURE_SCREENSHOTS = "1"
& "$PSScriptRoot\e2e.ps1" -BrowserChannel $BrowserChannel
if ($LASTEXITCODE -ne 0) { throw "Submission screenshot capture failed." }
Write-Host "Product screenshots saved under docs\screenshots. Capture the credentialed Cloud Run proof separately."
