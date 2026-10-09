# Serial chain for results/IIIA_AUG345_PROTOCOL.md: B3, P2-3, B4, P2-4, B5, P2-5.
# Each controller runs to completion before the next starts (controllers refuse to start while any
# other Python process exists). The first failure stops the chain; resumes are explicit, never automatic.
param([string]$Sentinel)
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path   # the repository root
$py = "C:\anaconda\python.exe"
$config = "claude/roadmap/configs/unit-ecom5.json"
$common = @("--config", $config, "--chunk-epochs", "12", "--trajectory-groups", "2", "--worker-timeout", "900")
$fixtures = @{
  "3" = "Opus_Fork/runs/20260922T225652Z-prepare-2026-08-03";
  "4" = "Opus_Fork/runs/20260922T230119Z-prepare-2026-08-04";
  "5" = "Opus_Fork/runs/20260922T230410Z-prepare-2026-08-05"
}
$status = Join-Path $root "Opus_Fork\runs\iiia345-chain.status"
Set-Location $root
foreach ($day in "3", "4", "5") {
  foreach ($arm in "B", "P2") {
    $label = "$arm-$day-25st"
    if ($arm -eq "B") { $args = @("-m", "Opus_Fork.run_fit", "--fixture", $fixtures[$day], "--label", $label) + $common }
    else { $args = @("-m", "Opus_Fork.run_fit_ngv", "--variant", "erp+thrust+iiia2600", "--fixture", $fixtures[$day], "--label", $label) + $common }
    $log = Join-Path $root "Opus_Fork\runs\iiia345-$label.log"
    Add-Content -Path $status -Value "$(Get-Date -Format o) START $label"
    $p = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru `
         -RedirectStandardOutput $log -RedirectStandardError ($log + ".err")
    Add-Content -Path $status -Value "$(Get-Date -Format o) END $label exit $($p.ExitCode)"
    if ($p.ExitCode -ne 0) {
      Add-Content -Path $status -Value "$(Get-Date -Format o) CHAIN STOPPED at $label"
      if ($Sentinel) { Remove-Item -LiteralPath $Sentinel -ErrorAction SilentlyContinue }
      exit 1
    }
  }
}
Add-Content -Path $status -Value "$(Get-Date -Format o) CHAIN COMPLETE"
if ($Sentinel) { Remove-Item -LiteralPath $Sentinel -ErrorAction SilentlyContinue }
