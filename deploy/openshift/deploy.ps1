# Rebuild the slim AI Skill Analyser image from this repo and roll it out
# on the OpenShift Developer Sandbox (or any project you are logged into).
#
# First time each day / after token expiry, copy the login command from
# the OpenShift console (User menu -> Copy login command) and run it, e.g.:
#   $env:USERPROFILE\bin\oc.exe login --token=... --server=https://api.rm3.7wse.p1.openshiftapps.com:6443
#
# Then, from the repo root:
#   .\deploy.cmd
#   powershell -File deploy\openshift\deploy.ps1
#
# After a 12-hour sandbox idle stop (no code changes):
#   .\restart-openshift.cmd
#   powershell -File deploy\openshift\deploy.ps1 -RestartOnly

[CmdletBinding()]
param(
    [switch]$RestartOnly
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$appYaml = Join-Path $PSScriptRoot "app.yaml"
$bcResources = Join-Path $PSScriptRoot "bc-resources.json"
$oc = $null
foreach ($candidate in @(
        (Join-Path $env:USERPROFILE "bin\oc.exe"),
        "oc.exe",
        "oc"
    )) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $oc = (Get-Command $candidate).Source
        break
    }
    if (Test-Path $candidate) {
        $oc = $candidate
        break
    }
}
if (-not $oc) {
    throw "oc CLI not found. Install it from the OpenShift console (Help -> Command line tools) or keep oc.exe in $env:USERPROFILE\bin"
}

function Invoke-Oc {
    param([Parameter(Mandatory = $true)][string[]]$OcArgs)
    & $oc @OcArgs
    if ($LASTEXITCODE -ne 0) {
        throw "oc $($OcArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Using oc: $oc"
$who = & $oc whoami 2>$null
if ($LASTEXITCODE -ne 0 -or -not $who) {
    throw "Not logged in. From the OpenShift console: User menu -> Copy login command, then run that oc login command and retry."
}
$project = (& $oc project -q).Trim()
Write-Host "Logged in as $who in project $project"

if ($RestartOnly) {
    Write-Host "Restarting the running app (no rebuild)..."
    Invoke-Oc -OcArgs @("rollout", "restart", "deployment/skill-analyser")
    Invoke-Oc -OcArgs @("rollout", "status", "deployment/skill-analyser", "--timeout=180s")
} else {
    $archive = Join-Path $env:TEMP "skill-analyser-os.tgz"
    if (Test-Path $archive) {
        Remove-Item $archive -Force
    }

    Write-Host "Packing $root (excluding venv, node_modules, git, local data)..."
    Push-Location $root
    try {
        tar -czf $archive `
            --exclude=.git `
            --exclude=.venv `
            --exclude=backend/.venv `
            --exclude=node_modules `
            --exclude=frontend/node_modules `
            --exclude=frontend/dist `
            --exclude=backend/storage `
            --exclude=storage `
            --exclude=*.db `
            --exclude=.env `
            --exclude=backend/.env `
            --exclude=__pycache__ `
            --exclude=.pytest_cache `
            .
        if ($LASTEXITCODE -ne 0) {
            throw "tar failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }

    & $oc get bc skill-analyser 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Creating binary Docker BuildConfig skill-analyser..."
        Invoke-Oc -OcArgs @("new-build", "--strategy=docker", "--binary", "--name=skill-analyser")
    }
    if (Test-Path $bcResources) {
        Invoke-Oc -OcArgs @("patch", "bc", "skill-analyser", "--type=merge", "--patch-file=$bcResources")
    }

    Write-Host "Building on the cluster (several minutes)..."
    Invoke-Oc -OcArgs @("start-build", "skill-analyser", "--from-archive=$archive", "--follow")

    Write-Host "Applying Deployment / Service / Route..."
    Invoke-Oc -OcArgs @("apply", "-f", $appYaml)
    $image = "image-registry.openshift-image-registry.svc:5000/${project}/skill-analyser:latest"
    Invoke-Oc -OcArgs @("set", "image", "deployment/skill-analyser", "app=$image")
    Invoke-Oc -OcArgs @("rollout", "restart", "deployment/skill-analyser")
    Invoke-Oc -OcArgs @("rollout", "status", "deployment/skill-analyser", "--timeout=180s")
}

$hostName = (& $oc get route skill-analyser -o jsonpath="{.spec.host}").Trim()
$url = "https://$hostName"
Write-Host ""
Write-Host "Deployed: $url"
Write-Host "Login:    admin@skillanalyser.ai / Admin@12345"
try {
    $health = Invoke-WebRequest -Uri "$url/api/health" -UseBasicParsing -TimeoutSec 30
    Write-Host "Health:   $($health.StatusCode) $($health.Content)"
} catch {
    Write-Host "Health check did not respond yet. Open the URL in a minute."
}
