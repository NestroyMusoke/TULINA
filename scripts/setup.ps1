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
if (-not (Test-Path "$root\.env")) { Copy-Item "$root\.env.example" "$root\.env" }
& $python -m pip install -e "$root[dev]"
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
& $npm ci --prefix "$root\frontend"
if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
& $python "$root\scripts\import_fixtures.py"
if ($LASTEXITCODE -ne 0) { throw "Fixture import failed." }
Write-Host "Tulina is ready. Run .\scripts\dev.ps1"
