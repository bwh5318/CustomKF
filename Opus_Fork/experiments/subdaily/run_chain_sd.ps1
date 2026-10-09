# Sub-daily EOP POD chain (results/SDEOP_PROTOCOL.md): SD arms on Aug 2, 7, 3, 4, 5, serial.
# Copy of experiments/ecom7/run_chain_e7p.ps1 with controller Opus_Fork.run_fit_sd and a per-step config.
# Limits and settings unchanged. Usage-ceiling / telemetry / memory-headroom / other-Python stops are waited out
# (GPU <50%, >= 6.5 GiB free and no Python process for 3 min) and resumed content-bound; anything else stops the
# chain; at most 20 resumes.
param([string]$Sentinel, [string[]]$Only)
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path   # the repository root
$py = "C:\anaconda\python.exe"
$runs = Join-Path $root "Opus_Fork\runs"
$status = Join-Path $runs "sdeop-chain.status"
$ecom5 = "claude/roadmap/configs/unit-ecom5.json"
$crossdate = "claude/experiments/cross_date_preparation/config.json"
$steps = @(
  @{label = "SD-2-25st"; variant = "erp+thrust+sdeop"; fixture = "Opus_Fork/runs/20260920T200910Z-prepare-31sat"; config = $ecom5; chunk = "12"; groups = "2"},
  @{label = "SD-7-25st"; variant = "erp+thrust+sdeop"; fixture = "runs/20260920T155655Z-7b703635"; config = $crossdate; chunk = "18"; groups = "4"},
  @{label = "SD-3-25st"; variant = "erp+thrust+iiia2600+sdeop"; fixture = "Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03"; config = $ecom5; chunk = "12"; groups = "2"},
  @{label = "SD-4-25st"; variant = "erp+thrust+iiia2600+sdeop"; fixture = "Opus_Fork/runs/20260922T230119Z-prepare-2026-08-04"; config = $ecom5; chunk = "12"; groups = "2"},
  @{label = "SD-5-25st"; variant = "erp+thrust+iiia2600+sdeop"; fixture = "Opus_Fork/runs/20260922T230410Z-prepare-2026-08-05"; config = $ecom5; chunk = "12"; groups = "2"}
)
if ($Only) { $steps = @($steps | Where-Object { $Only -contains $_.label }) }
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
  if ("$($v.error)" -match "Another Python process is running") { return $true }
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

foreach ($s in $steps) {
  $done = $false
  while (-not $done) {
    $existing = Campaign $s.label
    $argv = @("-m", "Opus_Fork.run_fit_sd", "--variant", $s.variant, "--fixture", $s.fixture, "--label", $s.label,
              "--config", $s.config, "--chunk-epochs", $s.chunk, "--trajectory-groups", $s.groups,
              "--worker-timeout", "900", "--max-linearizations", "6", "--protocol", "Opus_Fork/results/SDEOP_PROTOCOL.md")
    $tag = ""
    if ($existing) {
      $v = Get-Content (Join-Path $existing.FullName "validation.json") -Raw | ConvertFrom-Json
      if ($v.status -like "long_fit_complete*") { $done = $true; continue }
      $argv += @("--resume", $existing.FullName)
      $tag = " (resume)"
    }
    if (Get-Process python* -ErrorAction SilentlyContinue) { Wait-Quiet }
    $log = Join-Path $runs ("sdeop-" + $s.label + "-" + (Get-Date -Format "yyyyMMddTHHmmss") + ".log")
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
