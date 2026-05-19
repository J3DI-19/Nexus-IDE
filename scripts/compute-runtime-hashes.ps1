param(
  [string]$ManifestPath = "backend/config/runtime_manifest.json",
  [string[]]$Runtimes = @()
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $ManifestPath)) {
  throw "Manifest not found: $ManifestPath"
}

$manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$runtimeFilter = @()
foreach ($entry in $Runtimes) {
  if ($null -eq $entry) { continue }
  $parts = [string]$entry -split ','
  foreach ($part in $parts) {
    $name = $part.Trim().ToLowerInvariant()
    if ($name) {
      $runtimeFilter += $name
    }
  }
}
$runtimeFilter = $runtimeFilter | Select-Object -Unique

foreach ($name in $manifest.runtimes.PSObject.Properties.Name) {
  $runtimeName = [string]$name
  if ($runtimeFilter.Count -gt 0 -and ($runtimeFilter -notcontains $runtimeName.ToLowerInvariant())) {
    continue
  }
  $runtime = $manifest.runtimes.$runtimeName
  $win = $runtime.windows
  if (-not $win -or -not $win.url) {
    continue
  }

  $url = [string]$win.url
  if (-not $url.StartsWith("https://")) {
    Write-Host "Skipping $name (non-https): $url" -ForegroundColor Yellow
    continue
  }

  Write-Host "Hashing $name from $url"
  $tmp = [System.IO.Path]::GetTempFileName()
  try {
    try {
      Invoke-WebRequest -Uri $url -OutFile $tmp
      $hash = (Get-FileHash -Path $tmp -Algorithm SHA256).Hash.ToLowerInvariant()
      $manifest.runtimes.$name.windows.sha256 = $hash
      Write-Host "  sha256=$hash" -ForegroundColor Green
    } catch {
      Write-Host "  failed: $($_.Exception.Message)" -ForegroundColor Red
      continue
    }
  } finally {
    Remove-Item -Force $tmp -ErrorAction SilentlyContinue
  }
}

$json = $manifest | ConvertTo-Json -Depth 10
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Resolve-Path $ManifestPath), $json, $utf8NoBom)
Write-Host "Updated $ManifestPath"
