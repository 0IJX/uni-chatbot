$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runtime = Join-Path $root '.runtime'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null

function Get-LivePid {
  param([string]$PidFilePath)
  if (-not (Test-Path $PidFilePath)) { return 0 }
  $raw = (Get-Content -LiteralPath $PidFilePath -ErrorAction SilentlyContinue | Select-Object -First 1)
  $pidValue = 0
  if (-not [int]::TryParse([string]$raw, [ref]$pidValue)) {
    Remove-Item -LiteralPath $PidFilePath -Force -ErrorAction SilentlyContinue
    return 0
  }
  if ($pidValue -gt 0 -and (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
    return $pidValue
  }
  Remove-Item -LiteralPath $PidFilePath -Force -ErrorAction SilentlyContinue
  return 0
}

$python = Join-Path $root '.venv312\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

$backendPidFile = Join-Path $runtime 'backend.pid'
$frontendPidFile = Join-Path $runtime 'frontend.pid'

$backendStarted = $false
$frontendStarted = $false
$backendRunning = $false
$frontendRunning = $false

if (-not (Get-LivePid $backendPidFile)) {
  $backendOut = Join-Path $runtime 'backend.out.log'
  $backendErr = Join-Path $runtime 'backend.err.log'
  $backendProc = Start-Process -FilePath $python -ArgumentList 'backend/run.py' -WorkingDirectory $root -PassThru -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr -WindowStyle Hidden
  Set-Content -LiteralPath $backendPidFile -Value $backendProc.Id
  $backendStarted = $true
  $backendRunning = $true
} else {
  $backendRunning = $true
}

if (-not (Test-Path (Join-Path $root 'frontend/node_modules'))) {
  Push-Location (Join-Path $root 'frontend')
  npm.cmd install | Out-Host
  Pop-Location
}

if (-not (Get-LivePid $frontendPidFile)) {
  $frontendOut = Join-Path $runtime 'frontend.out.log'
  $frontendErr = Join-Path $runtime 'frontend.err.log'
  $frontendProc = Start-Process -FilePath 'npm.cmd' -ArgumentList 'run','dev' -WorkingDirectory (Join-Path $root 'frontend') -PassThru -RedirectStandardOutput $frontendOut -RedirectStandardError $frontendErr -WindowStyle Hidden
  Set-Content -LiteralPath $frontendPidFile -Value $frontendProc.Id
  $frontendStarted = $true
  $frontendRunning = $true
} else {
  $frontendRunning = $true
}

if ($backendStarted -or $frontendStarted) {
  Write-Output 'App stack started.'
} elseif ($backendRunning -and $frontendRunning) {
  Write-Output 'App stack already running.'
} else {
  Write-Output 'App stack partially running. Check ./status.'
}
Write-Output 'App URL: http://127.0.0.1:5173'
