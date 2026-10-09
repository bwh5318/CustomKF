# Gradient validation chain (Opus_Fork/experiments/gradients/VALIDATION_PROTOCOL.md, option A; user go-ahead 2 Oct 2026).
# Ten matched fits through Opus_Fork.run_fit_elev (fork8, campaign lease): the adopted default plus grad_op, then plus
# gpt3, on Jun 6, Jun 20, Jun 23, Jul 6 and Jul 23. The gradient source reaches every worker through OPUSFORK_GRADIENTS
# and is bound into each worker's force_model.json. Waits and the external-stop resume rule as run_chain_gradients.ps1.
param([string]$Sentinel, [string[]]$Only)
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path   # the repository root
$py = "C:\anaconda\python.exe"
$runs = Join-Path $root "Opus_Fork\runs"
$status = Join-Path $runs "gradval-chain.status"
$ecom5 = "claude/roadmap/configs/unit-ecom5.json"
$protocol = "Opus_Fork/experiments/gradients/VALIDATION_PROTOCOL.md"
$variant = "erp+thrust+iiia2600+sdeop+elw13"
$fixtures = @{ "0606" = "runs/20260929T202245Z-21f63ba3"; "0620" = "runs/20260929T203924Z-224f1e22";
               "0623" = "runs/20260929T201929Z-5b2b3e42"; "0706" = "runs/20260929T204645Z-ba94e895";
               "0723" = "runs/20260929T203059Z-40b5a8d7" }
$steps = @()
foreach ($g in @(@("op", "grad_op"), @("gpt3", "gpt3"))) {
  foreach ($d in @("0606", "0620", "0623", "0706", "0723")) {
    $steps += @{label = "V-$($g[0])-$d"; kind = "fit"; variant = $variant; gradients = $g[1]; fixture = $fixtures[$d]}
  }
}
if ($Only) { $Only = @($Only | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() }); $steps = @($steps | Where-Object { $Only -contains $_.label }) }
$resumes = 0
Set-Location $root

function Project-Campaign-Python {
  # This project's guard or campaign-controller Python processes only (user decision 3 Oct 2026). Other Python,
  # including other projects and this project's unguarded analyses, is governed by the hardware rules instead.
  foreach ($p in @(Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue)) {
    if ("$($p.CommandLine)" -match '-m\s+(customkf\.guard|Opus_Fork\.guard|Opus_Fork\.run_fit\w*)(\s|$)') { return $true }
  }
  return $false
}

function Wait-Quiet {
  Add-Content -Path $status -Value "$(Get-Date -Format o) WAITING for GPU load below 50%, >= 6.5 GiB free memory and no guard/controller Python of this project (3 min)"
  $quiet = 0
  while ($quiet -lt 6) {
    Start-Sleep -Seconds 30
    try {
      $by = @{}
      foreach ($x in (Get-Counter '\GPU Engine(*)\Utilization Percentage' -ErrorAction Stop).CounterSamples) {
        if ($x.InstanceName -match '(phys_\d+_eng_\d+)') { $by[$matches[1]] += $x.CookedValue }
      }
      $availGiB = (Get-Counter '\Memory\Available MBytes' -ErrorAction Stop).CounterSamples[0].CookedValue/1024
      $noPython = -not (Project-Campaign-Python)
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
      # A timeout whose elapsed wall time far exceeds its limit is the PC sleeping mid-worker (3 Oct 2026: 14,570 s
      # elapsed against 900 s, 47 CPU s); the worker resumes cleanly, so treat it as external.
      if ($r.status -eq "timeout" -and $r.limits -and [double]$r.elapsed_s -gt 1.5*[double]$r.limits.timeout_s) { return $true }
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
    $argv = @("-m", "Opus_Fork.run_fit_elev", "--variant", $s.variant, "--fixture", $s.fixture, "--label", $s.label,
              "--config", $ecom5, "--chunk-epochs", "12", "--trajectory-groups", "2",
              "--worker-timeout", "900", "--max-linearizations", "6", "--protocol", $protocol)
    $tag = ""
    if ($existing) {
      $v = Get-Content (Join-Path $existing.FullName "validation.json") -Raw | ConvertFrom-Json
      if ($v.status -like "long_fit_complete*") { $done = $true; continue }
      $argv += @("--resume", $existing.FullName)
      $tag = " (resume)"
    }
    if (Project-Campaign-Python) { Wait-Quiet }
    $env:OPUSFORK_GRADIENTS = $s.gradients
    $log = Join-Path $runs ("gradval-" + $s.label + "-" + (Get-Date -Format "yyyyMMddTHHmmss") + ".log")
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
