$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

& (Join-Path $root 'scripts/stop.ps1')

$targets = @(
  (Join-Path $root 'backend/data/runtime'),
  (Join-Path $root 'backend/data/uploads'),
  (Join-Path $root 'backend/data/artifacts')
)

foreach ($dir in $targets) {
  if (Test-Path $dir) {
    Get-ChildItem -LiteralPath $dir -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  }
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
  Set-Content -LiteralPath (Join-Path $dir '.gitkeep') -Value '' -NoNewline
  Write-Output ("Reset: cleared " + $dir)
}

Write-Output 'Runtime data reset complete (uploads/runtime/artifacts cleared, catalog preserved).'
