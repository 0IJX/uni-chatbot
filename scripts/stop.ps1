$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runtime = Join-Path $root '.runtime'

function Stop-ProcessTree {
  param([int]$RootId)
  if (-not $RootId) { return }

  $toStop = New-Object System.Collections.Generic.HashSet[int]
  $queue = New-Object System.Collections.Generic.Queue[int]
  $null = $toStop.Add($RootId)
  $queue.Enqueue($RootId)

  while ($queue.Count -gt 0) {
    $current = $queue.Dequeue()
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$current"
    foreach ($child in $children) {
      $cid = [int]$child.ProcessId
      if ($toStop.Add($cid)) {
        $queue.Enqueue($cid)
      }
    }
  }

  $ordered = $toStop | Sort-Object -Descending
  foreach ($id in $ordered) {
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
  }
}

$files = @('backend.pid','frontend.pid')
$stoppedAny = $false
foreach ($f in $files) {
  $p = Join-Path $runtime $f
  if (Test-Path $p) {
    $procId = [int](Get-Content $p)
    if ($procId) { Stop-ProcessTree -RootId $procId }
    Remove-Item $p -Force
    $stoppedAny = $true
  }
}

if ($stoppedAny) {
  Write-Output 'App stack stopped.'
} else {
  Write-Output 'App stack already stopped.'
}
