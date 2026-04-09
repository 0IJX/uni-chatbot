$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runtime = Join-Path $root '.runtime'

function Get-LivePid {
  param([string]$PidFilePath)
  if (-not (Test-Path $PidFilePath)) { return 0 }
  $raw = (Get-Content -LiteralPath $PidFilePath -ErrorAction SilentlyContinue | Select-Object -First 1)
  $pidValue = 0
  if (-not [int]::TryParse([string]$raw, [ref]$pidValue)) {
    Remove-Item -LiteralPath $PidFilePath -Force -ErrorAction SilentlyContinue
    return 0
  }
  if ($pidValue -gt 0 -and (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) { return $pidValue }
  Remove-Item -LiteralPath $PidFilePath -Force -ErrorAction SilentlyContinue
  return 0
}

$backendPid = Get-LivePid (Join-Path $runtime 'backend.pid')
$frontendPid = Get-LivePid (Join-Path $runtime 'frontend.pid')

Write-Output ("Backend: " + ($(if ($backendPid) {"running (PID $backendPid)"} else {"stopped"})))
Write-Output ("Frontend: " + ($(if ($frontendPid) {"running (PID $frontendPid)"} else {"stopped"})))

if ($frontendPid) {
  Write-Output 'App URL: http://127.0.0.1:5173'
}
