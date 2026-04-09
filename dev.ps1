param(
  [Parameter(Position=0)]
  [string]$Command = 'status'
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

switch ($Command.ToLower()) {
  'start' { & (Join-Path $root 'scripts/start.ps1') }
  'stop' { & (Join-Path $root 'scripts/stop.ps1') }
  'status' { & (Join-Path $root 'scripts/status.ps1') }
  'reset' { & (Join-Path $root 'scripts/reset.ps1') }
  'clean' { & (Join-Path $root 'scripts/clean.ps1') }
  default {
    Write-Host 'Usage: ./dev.ps1 [start|stop|status|reset|clean]'
    exit 1
  }
}
