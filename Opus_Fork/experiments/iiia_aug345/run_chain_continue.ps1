# Continuation of run_chain.ps1 after it stopped at B-4-25st on 2026-09-23T01:04Z.
# Cause: the guard's Windows GPU telemetry returned 0xc0000bba at worker start and the guard failed closed
# (status controller_failed, 0 s). B3 and P2-3 had completed. Telemetry verified working afterwards.
# Step 1 is an explicit, content-bound resume of the B-4 campaign (the failed worker is set aside and rerun,
# limits unchanged); then P2-4, B5, P2-5 exactly as in run_chain.ps1. First failure stops the chain.
param([string]$Sentinel, [string]$ResumeB4)
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path   # the repository root
$py = "C:\anaconda\python.exe"
$config = "claude/roadmap/configs/unit-ecom5.json"
$common = @("--config", $config, "--chunk-epochs", "12", "--trajectory-groups", "2", "--worker-timeout", "900")
$fixtures = @{
  "4" = "Opus_Fork/runs/20260922T230119Z-prepare-2026-08-04";
  "5" = "Opus_Fork/runs/20260922T230410Z-prepare-2026-08-05"
}
$status = Join-Path $root "Opus_Fork\runs\iiia345-chain.status"
Set-Location $root
$steps = @(
  @{label = "B-4-25st"; args = @("-m", "Opus_Fork.run_fit", "--fixture", $fixtures["4"], "--label", "B-4-25st") + $common + @("--resume", $ResumeB4); log = "iiia345-B-4-25st-resume"},
  @{label = "P2-4-25st"; args = @("-m", "Opus_Fork.run_fit_ngv", "--variant", "erp+thrust+iiia2600", "--fixture", $fixtures["4"], "--label", "P2-4-25st") + $common; log = "iiia345-P2-4-25st"},
  @{label = "B-5-25st"; args = @("-m", "Opus_Fork.run_fit", "--fixture", $fixtures["5"], "--label", "B-5-25st") + $common; log = "iiia345-B-5-25st"},
  @{label = "P2-5-25st"; args = @("-m", "Opus_Fork.run_fit_ngv", "--variant", "erp+thrust+iiia2600", "--fixture", $fixtures["5"], "--label", "P2-5-25st") + $common; log = "iiia345-P2-5-25st"}
)
foreach ($s in $steps) {
  $log = Join-Path $root ("Opus_Fork\runs\" + $s.log + ".log")
  Add-Content -Path $status -Value "$(Get-Date -Format o) START $($s.label)$(if ($s.log -like '*resume') {' (resume)'})"
  $p = Start-Process -FilePath $py -ArgumentList $s.args -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru `
       -RedirectStandardOutput $log -RedirectStandardError ($log + ".err")
  Add-Content -Path $status -Value "$(Get-Date -Format o) END $($s.label) exit $($p.ExitCode)"
  if ($p.ExitCode -ne 0) {
    Add-Content -Path $status -Value "$(Get-Date -Format o) CHAIN STOPPED at $($s.label)"
    if ($Sentinel) { Remove-Item -LiteralPath $Sentinel -ErrorAction SilentlyContinue }
    exit 1
  }
}
Add-Content -Path $status -Value "$(Get-Date -Format o) CHAIN COMPLETE"
if ($Sentinel) { Remove-Item -LiteralPath $Sentinel -ErrorAction SilentlyContinue }
