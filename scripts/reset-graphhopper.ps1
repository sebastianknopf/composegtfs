# reset-graphhopper.ps1
# Stops the GraphHopper service, removes its data volume, and restarts it.
# Run from the project root or any subdirectory.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Resolve project root (one level up from this script's directory)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot

try {
    Write-Host "==> Stopping GraphHopper service..." -ForegroundColor Cyan
    docker compose --profile graphhopper stop graphhopper

    Write-Host "==> Removing GraphHopper container..." -ForegroundColor Cyan
    docker compose --profile graphhopper rm -f graphhopper

    Write-Host "==> Removing GraphHopper data volume..." -ForegroundColor Cyan
    $ProjectName = (Split-Path -Leaf $ProjectRoot).ToLower()
    $removed = $false
    docker volume rm "${ProjectName}_graphhopper_data" 2>$null
    if ($LASTEXITCODE -eq 0) { $removed = $true }
    if (-not $removed) {
        # Fallback: try with the raw volume name as defined in compose
        docker volume rm graphhopper_data 2>$null
    }

    Write-Host "==> Starting GraphHopper service..." -ForegroundColor Cyan
    docker compose --profile graphhopper up -d graphhopper

    Write-Host "==> Done. GraphHopper is starting up." -ForegroundColor Green
    Write-Host "    Follow logs with: docker compose --profile graphhopper logs -f graphhopper"
} finally {
    Pop-Location
}
