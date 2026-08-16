param(
  [Parameter(Mandatory = $true)][string]$Action,
  [Parameter(Mandatory = $true)][string]$Fqdn,
  [Parameter(Mandatory = $true)][string]$Token
)

$stateDir = Join-Path $env:TEMP "acme-dns"
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$challengeFile = Join-Path $stateDir "challenge.json"
$readyFile = Join-Path $stateDir "ready.flag"

$payload = @{
  action    = $Action
  fqdn      = $Fqdn
  token     = $Token
  updatedAt = (Get-Date).ToString("o")
} | ConvertTo-Json
Set-Content -Path $challengeFile -Value $payload -Encoding utf8

if ($Action -eq "present") {
  Remove-Item -Path $readyFile -ErrorAction SilentlyContinue
  $deadline = (Get-Date).AddMinutes(8)
  while (-not (Test-Path $readyFile)) {
    if ((Get-Date) -gt $deadline) {
      Write-Error "Timed out waiting for $readyFile"
      exit 1
    }
    Start-Sleep -Seconds 3
  }
  # Extra wait so GoDaddy DNS can propagate to Let's Encrypt resolvers.
  Start-Sleep -Seconds 45
  exit 0
}

exit 0
