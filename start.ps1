# Run: pwsh -ExecutionPolicy Bypass -File start.ps1
$ErrorActionPreference = 'Stop'
docker compose up -d
docker compose logs -f gateway
