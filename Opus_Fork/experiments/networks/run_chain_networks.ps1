# Station-network tests (Opus_Fork/experiments/networks/PROTOCOL.md; user request 5 Oct 2026). Fits through
# Opus_Fork.run_fit_elev (fork8, campaign lease), the best configuration (default + GRAD operational gradients):
# S17-op on the five dates; then (amendment A2, 7 Oct) the parity fit E-check-0620 with --eliminate-ambiguities, the
# guarded parity check (the chain stops if it fails), and S50e-op on the five dates with --eliminate-ambiguities.
# A completed fit or a passed parity check is skipped. Waits and the external-stop resume rule as run_chain_gradval.ps1.
param([string]$Sentinel, [string[]]$Only)
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path   # the repository root
$py = "C:\anaconda\python.exe"
$runs = Join-Path $root "Opus_Fork\runs"
$status = Join-Path $runs "networks-chain.status"
$ecom5 = "claude/roadmap/configs/unit-ecom5.json"
$protocol = "Opus_Fork/experiments/networks/PROTOCOL.md"
$variant = "erp+thrust+iiia2600+sdeop+elw13"
$fixtures = @{ "S17-0606" = "runs/20261005T211928Z-aa4c3116"; "S17-0620" = "runs/20261005T212204Z-91e9588f"; "S17-0623" = "runs/20261005T212446Z-d478a2b1";
               "S17-0706" = "runs/20261005T212732Z-12a61896"; "S17-0723" = "runs/20261005T213015Z-dee9369b";
               "S50-0606" = "runs/20261005T213259Z-5fa3ee14"; "S50-0620" = "runs/20261005T213621Z-756c1841"; "S50-0623" = "runs/20261005T213957Z-fe592460";
               "S50-0706" = "runs/20261005T214600Z-31ee7e8d"; "S50-0723" = "runs/20261005T210900Z-85424435" }
$steps = @()
foreach ($d in @("0606", "0620", "0623", "0706", "0723")) {
  $steps += @{label = "S17-op-$d"; kind = "fit"; variant = $variant; gradients = "grad_op"; fixture = $fixtures["S17-$d"]; eliminate = $false}
}
$steps += @{label = "E-check-0620"; kind = "fit"; variant = $variant; gradients = "grad_op"; fixture = "runs/20260929T203924Z-224f1e22"; eliminate = $true}
$steps += @{label = "PARITY"; kind = "parity"}
foreach ($d in @("0606", "0620", "0623", "0706", "0723")) {
  $steps += @{label = "S50e-op-$d"; kind = "fit"; variant = $variant; gradients = "grad_op"; fixture = $fixtures["S50-$d"]; eliminate = $true}
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
    if ($s.kind -eq "parity") {
      if (Select-String -Path $status -Pattern "DONE PARITY passed" -Quiet -ErrorAction SilentlyContinue) { $done = $true; continue }
      if (Project-Campaign-Python) { Wait-Quiet }
      $log = Join-Path $runs ("networks-parity-" + (Get-Date -Format "yyyyMMddTHHmmss") + ".log")
      Add-Content -Path $status -Value "$(Get-Date -Format o) START PARITY"
      $argv = @("-m", "customkf.guard", "--profile", "usage75", "--threads", "1", "--timeout", "900", "--",
                "Opus_Fork.experiments.networks.parity_check")
      $p = Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru `
           -RedirectStandardOutput $log -RedirectStandardError ($log + ".err")
      $text = Get-Content $log -Raw -ErrorAction SilentlyContinue
      if ($p.ExitCode -eq 0) {
        Add-Content -Path $status -Value "$(Get-Date -Format o) DONE PARITY passed ($log)"
        $done = $true; continue
      }
      if (($text -match "REFUSED|LeaseHeld|memory headroom|usage_limit") -and $resumes -lt 20) {
        $resumes += 1
        Add-Content -Path $status -Value "$(Get-Date -Format o) PARITY guard refused or stopped externally; retry $resumes of 20 after quiet period"
        Wait-Quiet; continue
      }
      Add-Content -Path $status -Value "$(Get-Date -Format o) CHAIN STOPPED at PARITY (check failed or errored: $log); no S50 fit runs"
      if ($Sentinel) { Remove-Item -LiteralPath $Sentinel -ErrorAction SilentlyContinue }
      exit 1
    }
    $existing = Campaign $s.label
    $argv = @("-m", "Opus_Fork.run_fit_elev", "--variant", $s.variant, "--fixture", $s.fixture, "--label", $s.label,
              "--config", $ecom5, "--chunk-epochs", "12", "--trajectory-groups", "2",
              "--worker-timeout", "900", "--max-linearizations", "6", "--protocol", $protocol)
    if ($s.eliminate) { $argv += @("--eliminate-ambiguities") }
    $tag = ""
    if ($existing) {
      $v = Get-Content (Join-Path $existing.FullName "validation.json") -Raw | ConvertFrom-Json
      if ($v.status -like "long_fit_complete*") { $done = $true; continue }
      $argv += @("--resume", $existing.FullName)
      $tag = " (resume)"
    }
    if (Project-Campaign-Python) { Wait-Quiet }
    $env:OPUSFORK_GRADIENTS = $s.gradients
    $log = Join-Path $runs ("networks-" + $s.label + "-" + (Get-Date -Format "yyyyMMddTHHmmss") + ".log")
    Add-Content -Path $status -Value "$(Get-Date -Format o) START $($s.label)$tag (gradients $($s.gradients))"
    $p = Start-Process -FilePath $py -ArgumentList $argv -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru `
         -RedirectStandardOutput $log -RedirectStandardError ($log + ".err")
    Remove-Item Env:OPUSFORK_GRADIENTS -ErrorAction SilentlyContinue
    Add-Content -Path $status -Value "$(Get-Date -Format o) END $($s.label) exit $($p.ExitCode)"
    if ($p.ExitCode -eq 0) { $done = $true; continue }
    # Another guarded job took the machine lease at the moment the controller started (5 Oct 2026: a report build won
    # that race). The controller is refused before it writes anything, so wait for quiet and try again.
    if ((Get-Content ($log + ".err") -Raw -ErrorAction SilentlyContinue) -match "LeaseHeld" -and $resumes -lt 20) {
      $resumes += 1
      Add-Content -Path $status -Value "$(Get-Date -Format o) campaign lease held by another job at start; retry $resumes of 20 after quiet period"
      Wait-Quiet
      continue
    }
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
