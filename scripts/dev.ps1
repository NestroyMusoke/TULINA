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
Start-Process -WindowStyle Hidden -FilePath $python -ArgumentList "-m", "uvicorn", "backend.tulina.api:app", "--host", "0.0.0.0", "--port", "8080", "--reload" -WorkingDirectory $root
& $npm --prefix "$root\frontend" run dev
