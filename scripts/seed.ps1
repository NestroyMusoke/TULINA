$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\X1 Yoga\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
Push-Location $root
try {
    & $python -m backend.tulina.cli seed --reset
} finally {
    Pop-Location
}
