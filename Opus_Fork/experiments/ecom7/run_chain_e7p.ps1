# Constrained ECOM-7 chain (results/ECOM7P_PROTOCOL.md, ECOM7P_HOLDOUT_PROTOCOL.md): E7P arms on Aug 2, 3, then held-out 4, 5, 7, serial.
# Copy of run_chain_e7.ps1 with the prior config and new labels. Limits and settings unchanged; only
# usage-ceiling / telemetry / memory-headroom stops are waited out (GPU <50% and >= 6.5 GiB free for 3 min)
# and resumed content-bound; anything else stops the chain; at most 20 resumes.
param([string]$Sentinel, [string[]]$Only)
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path   # the repository root
$py = "C:\anaconda\python.exe"
$runs = Join-Path $root "Opus_Fork\runs"
$status = Join-Path $runs "ecom7p-chain.status"
$config = "Opus_Fork/experiments/ecom7/config_ecom7_prior2.json"
$steps = @(
  @{label = "E7P-2-25st"; variant = "erp+thrust+ecom7"; fixture = "Opus_Fork/runs/20260920T200910Z-prepare-31sat"; chunk = "12"; groups = "2"},
  @{label = "E7P-3-25st"; variant = "erp+thrust+iiia2600+ecom7"; fixture = "Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03"; chunk = "12"; groups = "2"},
  # Held-out days (results/ECOM7P_HOLDOUT_PROTOCOL.md), appended 25 Sep; each uses its ECOM5 comparator's ERP variant.
  @{label = "E7P-4-25st"; variant = "erp+thrust+iiia2600+ecom7"; fixture = "Opus_Fork/runs/20260922T230119Z-prepare-2026-08-04"; chunk = "12"; groups = "2"},
  @{label = "E7P-5-25st"; variant = "erp+thrust+iiia2600+ecom7"; fixture = "Opus_Fork/runs/20260922T230410Z-prepare-2026-08-05"; chunk = "12"; groups = "2"},
  @{label = "E7P-7-25st"; variant = "erp+thrust+ecom7"; fixture = "runs/20260920T155655Z-7b703635"; chunk = "12"; groups = "2"}
)
if ($Only) { $steps = @($steps | Where-Object { $Only -contains $_.label }) }
$resumes = 0
Set-Location $root

function Wait-Quiet {
  # 25 Sep: also waits for no Python process at all (another project's Python made the guard refuse E7P-3's
  # next worker). The guard's other-Python rule is kept; the chain just waits it out instead of stopping.
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
    $argv = @("-m", "Opus_Fork.run_fit_e7", "--variant", $s.variant, "--fixture", $s.fixture, "--label", $s.label,
              "--config", $config, "--chunk-epochs", $s.chunk, "--trajectory-groups", $s.groups,
              "--worker-timeout", "900", "--max-linearizations", "6")
    $tag = ""
    if ($existing) {
      $v = Get-Content (Join-Path $existing.FullName "validation.json") -Raw | ConvertFrom-Json
      if ($v.status -like "long_fit_complete*") { $done = $true; continue }
      $argv += @("--resume", $existing.FullName)
      $tag = " (resume)"
    }
    if (Get-Process python* -ErrorAction SilentlyContinue) { Wait-Quiet }
    $log = Join-Path $runs ("ecom7p-" + $s.label + "-" + (Get-Date -Format "yyyyMMddTHHmmss") + ".log")
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
