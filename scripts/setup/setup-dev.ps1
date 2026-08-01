# Bootstrap the AgencyOS workspace on Windows PowerShell.
# Copies env templates and ensures storage directories exist.
# Usage: scripts/setup/setup-dev.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

function Copy-IfMissing($Source, $Destination) {
    if (-not (Test-Path -LiteralPath $Destination)) {
        Copy-Item -LiteralPath $Source -Destination $Destination
        Write-Host "created $Destination"
    } else {
        Write-Host "exists  $Destination"
    }
}

Copy-IfMissing (Join-Path $Root ".env.example")         (Join-Path $Root ".env")
Copy-IfMissing (Join-Path $Root "backend\.env.example") (Join-Path $Root "backend\.env")
Copy-IfMissing (Join-Path $Root "frontend\.env.example")(Join-Path $Root "frontend\.env.local")

foreach ($dir in @("storage\uploads", "storage\exports", "storage\logs", "storage\backups")) {
    $path = Join-Path $Root $dir
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    New-Item -ItemType File -Force -Path (Join-Path $path ".gitkeep") | Out-Null
}

Write-Host "AgencyOS workspace ready. Edit the created .env files with real values."
