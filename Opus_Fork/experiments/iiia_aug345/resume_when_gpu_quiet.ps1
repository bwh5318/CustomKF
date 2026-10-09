# Wait until external GPU load has cleared, then relaunch run_chain_continue.ps1 once.
# The guard's 75% machine ceiling is unchanged and still enforced on every worker; this only avoids
# relaunching into a load that would stop the first worker again. Quiet = the busiest physical GPU
# engine, summed across processes (the guard's own measure), below 50% for 6 consecutive 30 s samples.
param([string]$Sentinel, [string]$ResumeB4)
$status = (Join-Path $PSScriptRoot "..\..\runs\iiia345-chain.status")
Add-Content -Path $status -Value "$(Get-Date -Format o) WAITING for GPU load below 50% (3 min) before resume"
$quiet = 0
while ($quiet -lt 6) {
  Start-Sleep -Seconds 30
  try {
    $samples = (Get-Counter '\GPU Engine(*)\Utilization Percentage' -ErrorAction Stop).CounterSamples
    $byEngine = @{}
    foreach ($x in $samples) {
      if ($x.InstanceName -match '(phys_\d+_eng_\d+)') { $byEngine[$matches[1]] += $x.CookedValue }
    }
    $busiest = ($byEngine.Values | Measure-Object -Maximum).Maximum
    if ($busiest -lt 50) { $quiet += 1 } else { $quiet = 0 }
  } catch { $quiet = 0 }
}
Add-Content -Path $status -Value "$(Get-Date -Format o) GPU quiet; relaunching continuation"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "run_chain_continue.ps1") -Sentinel $Sentinel -ResumeB4 $ResumeB4
