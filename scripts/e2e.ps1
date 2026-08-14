param(
    [string]$BrowserChannel = "chrome"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root "frontend"
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$python = if (Test-Path $bundledPython) { $bundledPython } elseif ($pythonCommand) { $pythonCommand.Source } else { $null }
if (-not $python) { throw "Python 3.12 was not found. Run scripts\setup.ps1 first." }
if (-not $nodeCommand -or -not $npmCommand) { throw "Node.js 22 with npm was not found. Run scripts\setup.ps1 first." }

function Test-TulinaEndpoint([string]$Url) {
    try {
        return (Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2).StatusCode -eq 200
    } catch {
        return $false
    }
}

$apiProcess = $null
$webProcess = $null
$env:TULINA_MODE = "fixture"
$env:TULINA_QUEUE = "local"
$env:TULINA_AGENT_STEP_DELAY_MS = "0"
$env:TULINA_DATABASE_PATH = Join-Path $root "work\e2e.sqlite3"
$env:TULINA_E2E_PYTHON = $python
if ($BrowserChannel) {
    $env:TULINA_E2E_BROWSER_CHANNEL = $BrowserChannel
} else {
    Remove-Item Env:TULINA_E2E_BROWSER_CHANNEL -ErrorAction SilentlyContinue
}

try {
    if (-not (Test-TulinaEndpoint "http://127.0.0.1:8080/readyz")) {
        $apiProcess = Start-Process -PassThru -WindowStyle Hidden -FilePath $python -ArgumentList "-m", "uvicorn", "backend.tulina.api:app", "--host", "127.0.0.1", "--port", "8080" -WorkingDirectory $root
    }
    if (-not (Test-TulinaEndpoint "http://127.0.0.1:5173/judge")) {
        $vite = Join-Path $frontend "node_modules\vite\bin\vite.js"
        if (-not (Test-Path $vite)) { throw "Frontend dependencies are missing. Run scripts\setup.ps1 first." }
        $quotedVite = '"' + $vite + '"'
        $webProcess = Start-Process -PassThru -WindowStyle Hidden -FilePath $nodeCommand.Source -ArgumentList $quotedVite, "--host", "127.0.0.1", "--port", "5173" -WorkingDirectory $frontend
    }

    $apiReady = $false
    $webReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt += 1) {
        $apiReady = Test-TulinaEndpoint "http://127.0.0.1:8080/readyz"
        $webReady = Test-TulinaEndpoint "http://127.0.0.1:5173/judge"
        if ($apiReady -and $webReady) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $apiReady) { throw "The Tulina API did not become ready on port 8080." }
    if (-not $webReady) { throw "The Tulina PWA did not become ready on port 5173." }

    & $npmCommand.Source --prefix $frontend run test:e2e
    if ($LASTEXITCODE -ne 0) { throw "Browser E2E verification failed." }
} finally {
    if ($webProcess -and -not $webProcess.HasExited) { Stop-Process -Id $webProcess.Id -Force }
    if ($apiProcess -and -not $apiProcess.HasExited) { Stop-Process -Id $apiProcess.Id -Force }
}
