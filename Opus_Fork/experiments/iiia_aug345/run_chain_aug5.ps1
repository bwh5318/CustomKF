# Aug-5 IIIA_AUG345 arms (B5 resumed, P2-5) with waits for external machine load.
# Written 23 Sep 2026 after two stops caused by other applications' GPU use (75% guard ceiling) and one
# by a transient Windows GPU-telemetry error. Policy:
#  - limits, ceilings and every scientific setting are unchanged; each resume is the controllers'
#    content-bound --resume (completed workers re-verified by hash, the stopped worker rerun);
#  - a stop is resumed automatically ONLY if the failed worker's status is a usage-ceiling stop or its error is
#    a usage-ceiling / telemetry refusal; the chain first waits for 3 quiet minutes (busiest GPU engine <50%);
#  - any other failure (numerical, line search, pins, cap) stops the chain for inspection;
#  - at most 20 automatic resumes in total.
# Aug-5 variant: cap of 6 linearizations for both arms (protocol amendment, 23 Sep 2026).
param([string]$Sentinel)
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path   # the repository root
$py = "C:\anaconda\python.exe"
$runs = Join-Path $root "Opus_Fork\runs"
$status = Join-Path $runs "iiia345-chain.status"
$common = @("--config", "claude/roadmap/configs/unit-ecom5.json", "--chunk-epochs", "12", "--trajectory-groups", "2", "--worker-timeout", "900", "--max-linearizations", "6")
$steps = @(
  @{label = "B-5-25st"; module = "Opus_Fork.run_fit"; fixture = "Opus_Fork/runs/20260922T230410Z-prepare-2026-08-05"},
  @{label = "P2-5-25st"; module = "Opus_Fork.run_fit_ngv"; fixture = "Opus_Fork/runs/20260922T230410Z-prepare-2026-08-05"}
)
$resumes = 0
Set-Location $root

function Wait-Quiet {
  Add-Content -Path $status -Value "$(Get-Date -Format o) WAITING for GPU load below 50% (3 min)"
  $quiet = 0
  while ($quiet -lt 6) {
    Start-Sleep -Seconds 30
    try {
      $by = @{}
      foreach ($x in (Get-Counter '\GPU Engine(*)\Utilization Percentage' -ErrorAction Stop).CounterSamples) {
        if ($x.InstanceName -match '(phys_\d+_eng_\d+)') { $by[$matches[1]] += $x.CookedValue }
      }
      if ((($by.Values | Measure-Object -Maximum).Maximum) -lt 50) { $quiet += 1 } else { $quiet = 0 }
    } catch { $quiet = 0 }
  }
  Add-Content -Path $status -Value "$(Get-Date -Format o) GPU quiet"
}

function Campaign($label) {
  Get-ChildItem $runs -Directory -Filter "*-fit-$label" | Sort-Object Name -Descending | Select-Object -First 1
}

function External-Stop($folder) {
  $v = Get-Content (Join-Path $folder.FullName "validation.json") -Raw | ConvertFrom-Json
  foreach ($p in $v.runs.PSObject.Properties) {
    $r = $p.Value
    if ($r.status -ne "ok") {
      if ($r.status -match "usage_limit") { return $true }
      if ("$($r.error)" -match "usage ceiling|telemetry") { return $true }
      return $false
    }
  }
  return $false
}

foreach ($s in $steps) {
  $done = $false
  while (-not $done) {
    $existing = Campaign $s.label
    $argv = @("-m", $s.module)
    if ($s.module -eq "Opus_Fork.run_fit_ngv") { $argv += @("--variant", "erp+thrust+iiia2600") }
    $argv += @("--fixture", $s.fixture, "--label", $s.label) + $common
    $tag = ""
    if ($existing) {
      $v = Get-Content (Join-Path $existing.FullName "validation.json") -Raw | ConvertFrom-Json
      if ($v.status -like "long_fit_complete*") { $done = $true; continue }
      $argv += @("--resume", $existing.FullName)
      $tag = " (resume)"
    }
    $log = Join-Path $runs ("iiia345-" + $s.label + "-" + (Get-Date -Format "yyyyMMddTHHmmss") + ".log")
    Add-Content -Path $status -Value "$(Get-Date -Format o) START $($s.label)$tag"
    $p = Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru `
         -RedirectStandardOutput $log -RedirectStandardError ($log + ".err")
    Add-Content -Path $status -Value "$(Get-Date -Format o) END $($s.label) exit $($p.ExitCode)"
    if ($p.ExitCode -eq 0) { $done = $true; continue }
    $folder = Campaign $s.label
    if ($folder -and (External-Stop $folder) -and $resumes -lt 20) {
      $resumes += 1
      Add-Content -Path $status -Value "$(Get-Date -Format o) external-load stop; automatic resume $resumes of 20 after quiet period"
      Wait-Quiet
      continue
    }
    Add-Content -Path $status -Value "$(Get-Date -Format o) CHAIN STOPPED at $($s.label) (not an external-load stop, or resume cap reached)"
    if ($Sentinel) { Remove-Item -LiteralPath $Sentinel -ErrorAction SilentlyContinue }
    exit 1
  }
}
Add-Content -Path $status -Value "$(Get-Date -Format o) CHAIN COMPLETE"
if ($Sentinel) { Remove-Item -LiteralPath $Sentinel -ErrorAction SilentlyContinue }
