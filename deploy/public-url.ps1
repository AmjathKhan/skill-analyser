# Publish the local app (Vite :5173 + API :8000) on a free HTTPS URL.
# No credit card. The URL changes each time this script runs.
# Usage (from the repo root, with frontend and backend already running):
#   powershell -File deploy\public-url.ps1

$ErrorActionPreference = "Stop"
$cloudflared = Join-Path $env:USERPROFILE ".cloudflared\cloudflared.exe"
if (-not (Test-Path $cloudflared)) {
    Write-Host "Downloading cloudflared..."
    New-Item -ItemType Directory -Force -Path (Split-Path $cloudflared) | Out-Null
    Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/download/2026.7.3/cloudflared-windows-amd64.exe" -OutFile $cloudflared -UseBasicParsing
}

Write-Host "Opening a public HTTPS URL to http://127.0.0.1:5173 ..."
Write-Host "Keep this window open. The URL is printed below when the tunnel is ready."
& $cloudflared tunnel --url http://127.0.0.1:5173
