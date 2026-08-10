$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) { throw "Node.js 22 with npm was not found. Install it and reopen PowerShell." }
$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$python = if (Test-Path $bundledPython) { $bundledPython } elseif ($pythonCommand) { $pythonCommand.Source } else { $null }
if (-not $python) { throw "Python 3.12 was not found. Install it and reopen PowerShell." }
& $python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Tulina requires Python 3.12 or newer." }
$npm = $npmCommand.Source
Push-Location $root
try {
    & $python scripts\verify_phase0.py
    if ($LASTEXITCODE -ne 0) { throw "Fixture and provenance verification failed." }
    & $python -m ruff check backend
    if ($LASTEXITCODE -ne 0) { throw "Backend lint failed." }
    & $python -m unittest discover -s backend\tests -v
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
    if (Test-Path "$root\frontend\tsconfig.json") {
        & $npm --prefix "$root\frontend" run lint
        if ($LASTEXITCODE -ne 0) { throw "Frontend lint failed." }
        & $npm --prefix "$root\frontend" run test
        if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
        & $npm --prefix "$root\frontend" run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
    }
} finally {
    Pop-Location
}
