Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Running backend syntax checks..."
python -m compileall backend

Write-Host "Running frontend lint..."
Push-Location frontend
try {
  npm run lint
  npm run lint:types
}
finally {
  Pop-Location
}

Write-Host "Lint checks completed."
