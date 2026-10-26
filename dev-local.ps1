# Runs Docling AI on this machine without Docker, each service in its own window:
#   FastAPI  on BACKEND_AI_PORT from .env (default 8000)
#   Express  on 3000
#   Vite     on 5173 (or the next free port)
# Close a window to stop that service. One-time setup: see "Run locally (without
# Docker)" in README.md.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venv = Join-Path $root '.venv'
$envFile = Join-Path $root '.env'

if (-not (Test-Path (Join-Path $venv 'python.exe'))) {
    throw "Python env not found at $venv. Run the one-time setup in README.md first."
}
if (-not (Select-String -Path $envFile -Pattern '^MONGO_URI=' -Quiet)) {
    throw "MONGO_URI is not set in $envFile"
}
$aiPort = (Select-String -Path $envFile -Pattern '^BACKEND_AI_PORT=(\d+)').Matches.Groups[1].Value
if (-not $aiPort) { $aiPort = '8000' }

# The browser calls FastAPI directly, so VITE_AI_URL must point at the port
# FastAPI actually binds (both come from .env).
$viteAiPort = (Select-String -Path $envFile -Pattern '^VITE_AI_URL=\S*?:(\d+)').Matches.Groups[1].Value
if ($viteAiPort -and $viteAiPort -ne $aiPort) {
    throw "VITE_AI_URL points at port $viteAiPort but BACKEND_AI_PORT is $aiPort. Make them match in $envFile."
}

# Check npm's install marker, not the folder: docker compose leaves an EMPTY
# backend\node_modules behind as a mount point for its node_modules volume.
foreach ($dir in 'backend', 'frontend') {
    if (-not (Test-Path (Join-Path $root "$dir\node_modules\.package-lock.json"))) {
        Write-Host "Installing $dir dependencies..."
        npm.cmd install --prefix (Join-Path $root $dir)
    }
}

foreach ($port in 3000, $aiPort) {
    $conn = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $owner = (Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)").CommandLine
        throw "Port $port is already in use by: $owner`nStop it, or (for the AI port) set BACKEND_AI_PORT in .env to a free port."
    }
}

function Start-Window($title, $command) {
    Start-Process powershell -WorkingDirectory $root -ArgumentList @(
        '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command',
        "`$Host.UI.RawUI.WindowTitle = '$title'; $command"
    )
}

# tectonic and pandoc live in .venv\Library\bin; the LaTeX features look them up on PATH.
Start-Window "Docling AI - FastAPI :$aiPort" "`$env:PATH = '$venv;$venv\Library\bin;$venv\Scripts;' + `$env:PATH; & '$venv\python.exe' -m backend_ai.main"
Start-Window 'Docling AI - Express :3000' 'npm.cmd start --prefix backend'

# Start Vite only once both backends accept connections; otherwise the browser's
# first requests hit a closed port and the Vite proxy turns them into 500s.
Write-Host 'Waiting for the backends...'
$deadline = (Get-Date).AddSeconds(90)
foreach ($port in 3000, $aiPort) {
    while (-not (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)) {
        if ((Get-Date) -gt $deadline) {
            throw "Nothing is listening on port $port after 90 s. Check that service's window for errors."
        }
        Start-Sleep -Milliseconds 500
    }
}
Start-Window 'Docling AI - Vite' 'npm.cmd run dev --prefix frontend'

Write-Host ''
Write-Host 'Started 3 windows. Open the "Local:" URL from the Vite window (normally http://localhost:5173).'
