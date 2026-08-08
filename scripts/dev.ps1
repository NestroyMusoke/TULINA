$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\X1 Yoga\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$pnpm = "C:\Users\X1 Yoga\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
Start-Process -WindowStyle Hidden -FilePath $python -ArgumentList "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080", "--reload" -WorkingDirectory $root
& $pnpm --dir "$root\frontend" dev

