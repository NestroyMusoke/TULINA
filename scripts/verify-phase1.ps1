$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\X1 Yoga\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
Push-Location $root
try {
    & $python scripts\verify_phase0.py
    & $python -m unittest discover -s backend\tests -v
    & $python -m compileall -q backend
    & $python -m backend.tulina.cli seed --database work\phase1-verify.sqlite3 --reset
} finally {
    Pop-Location
}
