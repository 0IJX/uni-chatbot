$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

& (Join-Path $root 'scripts/stop.ps1')

$targets = @(
  (Join-Path $root 'backend/data/runtime'),
  (Join-Path $root 'backend/data/uploads'),
  (Join-Path $root 'backend/data/artifacts'),
  (Join-Path $root 'frontend/dist'),
  (Join-Path $root '.runtime')
)

foreach ($target in $targets) {
  if (Test-Path $target) {
    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    Write-Output ("Clean: removed " + $target)
  }
}

foreach ($dir in @(
  (Join-Path $root 'backend/data/runtime'),
  (Join-Path $root 'backend/data/uploads'),
  (Join-Path $root 'backend/data/artifacts')
)) {
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
  Set-Content -LiteralPath (Join-Path $dir '.gitkeep') -Value '' -NoNewline
}

Write-Output 'Clean completed (runtime/uploads/artifacts/frontend dist/log runtime cleared, catalog preserved).'
