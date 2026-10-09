# Gradient experiment chain (Opus_Fork/experiments/gradients/PROTOCOL.md).
# Stage 1: the linear prediction worker under the root guard (usage75, one math thread).
# Stage 2: three matched Aug 3 fits through Opus_Fork.run_fit_elev (fork8, campaign lease). The gradient source
# reaches every worker through OPUSFORK_GRADIENTS and is bound into each worker's force_model.json.
# Same waits and external-stop resume rule as experiments/untouched_dates/run_chain_untouched.ps1.
param([string]$Sentinel, [string[]]$Only)
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path   # the repository root
$py = "C:\anaconda\python.exe"
$runs = Join-Path $root "Opus_Fork\runs"
$status = Join-Path $runs "gradients-chain.status"
$ecom5 = "claude/roadmap/configs/unit-ecom5.json"
$protocol = "Opus_Fork/experiments/gradients/PROTOCOL.md"
$fixture = "Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03"
$steps = @(
  @{label = "G-linear"; kind = "linear"},
  @{label = "G-op-e13"; kind = "fit"; variant = "erp+thrust+iiia2600+sdeop+elw13"; gradients = "grad_op"},
  @{label = "G-op-sd3"; kind = "fit"; variant = "erp+thrust+iiia2600+sdeop+none"; gradients = "grad_op"},
  @{label = "G-gpt3-e13"; kind = "fit"; variant = "erp+thrust+iiia2600+sdeop+elw13"; gradients = "gpt3"}
)
if ($Only) { $Only = @($Only | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() }); $steps = @($steps | Where-Object { $Only -contains $_.label }) }
$resumes = 0
Set-Location $root

function Wait-Quiet {
  Add-Content -Path $status -Value "$(Get-Date -Format o) WAITING for GPU load below 50%, >= 6.5 GiB free memory and no Python process (3 min)"
  $quiet = 0
  while ($quiet -lt 6) {
    Start-Sleep -Seconds 30
    try {
      $by = @{}
      foreach ($x in (Get-Counter '\GPU Engine(*)\Utilization Percentage' -ErrorAction Stop).CounterSamples) {
        if ($x.InstanceName -match '(phys_\d+_eng_\d+)') { $by[$matches[1]] += $x.CookedValue }
      }
      $availGiB = (Get-Counter '\Memory\Available MBytes' -ErrorAction Stop).CounterSamples[0].CookedValue/1024
      $noPython = -not (Get-Process python* -ErrorAction SilentlyContinue)
      if (((($by.Values | Measure-Object -Maximum).Maximum) -lt 50) -and ($availGiB -ge 6.5) -and $noPython) { $quiet += 1 } else { $quiet = 0 }
    } catch { $quiet = 0 }
  }
  Add-Content -Path $status -Value "$(Get-Date -Format o) quiet"
}

function Campaign($label) {
  Get-ChildItem $runs -Directory -Filter "*-fit-$label" | Sort-Object Name -Descending | Select-Object -First 1
}

function External-Stop($folder) {
  $v = Get-Content (Join-Path $folder.FullName "validation.json") -Raw | ConvertFrom-Json
  if ("$($v.error)" -match "Another Python process|memory headroom") { return $true }
  foreach ($p in $v.runs.PSObject.Properties) {
    $r = $p.Value
    if ($r.status -ne "ok") {
      if ($r.status -match "usage_limit") { return $true }
      if ("$($r.error)" -match "usage ceiling|telemetry|memory headroom") { return $true }
      return $false
    }
  }
  return $false
}

Wait-Quiet
foreach ($s in $steps) {
  $done = $false
  while (-not $done) {
    if ($s.kind -eq "linear") {
      if (Select-String -Path $status -Pattern "DONE G-linear" -Quiet -ErrorAction SilentlyContinue) { $done = $true; continue }
      $log = Join-Path $runs ("gradients-G-linear-" + (Get-Date -Format "yyyyMMddTHHmmss") + ".log")
      Add-Content -Path $status -Value "$(Get-Date -Format o) START G-linear"
      $argv = @("-m", "customkf.guard", "--profile", "usage75", "--threads", "1", "--timeout", "1800", "--",
                "Opus_Fork.experiments.gradients.transfer_grad")
      $p = Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru `
           -RedirectStandardOutput $log -RedirectStandardError ($log + ".err")
      $text = Get-Content $log -Raw -ErrorAction SilentlyContinue
      if ($p.ExitCode -eq 0) {
        $folder = if ($text -match "Logs: (\S+)") { $matches[1] } else { "?" }
        Add-Content -Path $status -Value "$(Get-Date -Format o) DONE G-linear $folder"
        $done = $true; continue
      }
      if (($text -match "memory headroom|usage_limit|Another customKF") -and $resumes -lt 20) {
        $resumes += 1
        Add-Content -Path $status -Value "$(Get-Date -Format o) G-linear external stop; retry $resumes of 20 after quiet period"
        Wait-Quiet; continue
      }
      # The fits do not depend on Stage 1: record the failure and continue. Any later fix of the Stage 1 worker is
      # then made after fit outcomes exist, and must be recorded as such (PROTOCOL.md amendment).
      Add-Content -Path $status -Value "$(Get-Date -Format o) G-linear FAILED (exit $($p.ExitCode)); continuing with the fits"
      $done = $true; continue
    }
    $existing = Campaign $s.label
    $argv = @("-m", "Opus_Fork.run_fit_elev", "--variant", $s.variant, "--fixture", $fixture, "--label", $s.label,
              "--config", $ecom5, "--chunk-epochs", "12", "--trajectory-groups", "2",
              "--worker-timeout", "900", "--max-linearizations", "6", "--protocol", $protocol)
    $tag = ""
    if ($existing) {
      $v = Get-Content (Join-Path $existing.FullName "validation.json") -Raw | ConvertFrom-Json
      if ($v.status -like "long_fit_complete*") { $done = $true; continue }
      $argv += @("--resume", $existing.FullName)
      $tag = " (resume)"
    }
    if (Get-Process python* -ErrorAction SilentlyContinue) { Wait-Quiet }
    $env:OPUSFORK_GRADIENTS = $s.gradients
    $log = Join-Path $runs ("gradients-" + $s.label + "-" + (Get-Date -Format "yyyyMMddTHHmmss") + ".log")
    Add-Content -Path $status -Value "$(Get-Date -Format o) START $($s.label)$tag (gradients $($s.gradients))"
    $p = Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru `
         -RedirectStandardOutput $log -RedirectStandardError ($log + ".err")
    Remove-Item Env:OPUSFORK_GRADIENTS -ErrorAction SilentlyContinue
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
