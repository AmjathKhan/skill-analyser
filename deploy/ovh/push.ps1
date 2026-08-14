# Copy this repo to an OVH Ubuntu VM and run the bootstrap script.
# Usage (from the repo root):
#   powershell -File deploy\ovh\push.ps1 -Server 51.xxx.xxx.xxx -User ubuntu
param(
    [Parameter(Mandatory = $true)]
    [string]$Server,
    [string]$User = "ubuntu",
    [string]$RemoteDir = "~/iim-project"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$archive = Join-Path $env:TEMP "iim-project-ovh.tgz"

Write-Host "Packing $root (excluding venv, node_modules, git)..."
Push-Location $root
try {
    tar -czf $archive --exclude=.git --exclude=.venv --exclude=backend/.venv --exclude=node_modules --exclude=frontend/node_modules --exclude=frontend/dist --exclude=backend/storage --exclude=storage --exclude=*.db --exclude=.env .
} finally {
    Pop-Location
}

Write-Host "Uploading to ${User}@${Server}:${RemoteDir} ..."
ssh -o StrictHostKeyChecking=accept-new "${User}@${Server}" "mkdir -p $RemoteDir"
scp $archive "${User}@${Server}:${RemoteDir}/bundle.tgz"
ssh "${User}@${Server}" "cd $RemoteDir && tar -xzf bundle.tgz && rm bundle.tgz && chmod +x deploy/ovh/bootstrap.sh && bash deploy/ovh/bootstrap.sh"

Remove-Item $archive -ErrorAction SilentlyContinue
Write-Host "Done. Open http://${Server} after the stack finishes starting."
