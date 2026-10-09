# Resume (or start) a fork fit chain after the PC was switched off or the session ended.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File <repository>\Opus_Fork\resume_chain.ps1 -Chain ecom7
#
# Every chain script skips completed fits and resumes an interrupted one content-bound (completed workers are
# re-verified by hash and reused; only the interrupted worker reruns), so a hard stop loses at most one worker.
# This helper refuses to start while a guard or campaign controller of this project is running (any Python process
# until 3 Oct 2026; user decision), holds a keep-awake request while the chain runs,
# and appends a RESUMED line to the chain's status log. Stop it any time: close the PC, or kill the chain.
param([Parameter(Mandatory = $true)][ValidateSet("ecom7", "ecom7p", "sdeop", "sens", "elev", "untouched", "gradients", "gradval", "newdate", "networks")][string]$Chain, [string]$Only, [switch]$WaitIfBusy)
# -Only "E7-3-25st" (comma-separated) resumes just those fits of the chain.
# -WaitIfBusy (ecom7p and sdeop): if a non-campaign Python process (e.g. another project's) is running, start anyway;
# the chain waits until no Python process has existed for 3 min before starting each fit.
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path   # the repository root
$scripts = @{
  "ecom7" = @{ script = "Opus_Fork\experiments\ecom7\run_chain_e7.ps1"; status = "Opus_Fork\runs\ecom7-chain.status" };
  "ecom7p" = @{ script = "Opus_Fork\experiments\ecom7\run_chain_e7p.ps1"; status = "Opus_Fork\runs\ecom7p-chain.status" };
  "sdeop" = @{ script = "Opus_Fork\experiments\subdaily\run_chain_sd.ps1"; status = "Opus_Fork\runs\sdeop-chain.status" };
  "sens" = @{ script = "Opus_Fork\experiments\sensitivity\run_chain_sens.ps1"; status = "Opus_Fork\runs\sens-chain.status" };
  "elev" = @{ script = "Opus_Fork\experiments\sensitivity\run_chain_elev.ps1"; status = "Opus_Fork\runs\elev-chain.status" };
  "untouched" = @{ script = "Opus_Fork\experiments\untouched_dates\run_chain_untouched.ps1"; status = "Opus_Fork\runs\untouched-chain.status" };
  "gradients" = @{ script = "Opus_Fork\experiments\gradients\run_chain_gradients.ps1"; status = "Opus_Fork\runs\gradients-chain.status" };
  "gradval" = @{ script = "Opus_Fork\experiments\gradients\run_chain_gradval.ps1"; status = "Opus_Fork\runs\gradval-chain.status" };
  "newdate" = @{ script = "Opus_Fork\experiments\gradients\run_chain_newdate.ps1"; status = "Opus_Fork\runs\newdate-chain.status" };
  "networks" = @{ script = "Opus_Fork\experiments\networks\run_chain_networks.ps1"; status = "Opus_Fork\runs\networks-chain.status" }
}
$c = $scripts[$Chain]
$campaignPython = @(Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue |
  Where-Object { "$($_.CommandLine)" -match '-m\s+(customkf\.guard|Opus_Fork\.guard|Opus_Fork\.run_fit\w*)(\s|$)' })
if ($campaignPython.Count -and -not ($WaitIfBusy -and $Chain -ne "ecom7")) { Write-Output "A guard or campaign controller of this project is running (pid $($campaignPython.ProcessId -join ', ')); inspect it before resuming (or pass -WaitIfBusy for ecom7p/sdeop)."; exit 1 }
$sentinel = Join-Path $env:TEMP "opusfork-keepawake-$Chain.sentinel"
Set-Content -Path $sentinel -Value "$Chain chain" -Encoding utf8
Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $root "claude\roadmap\keep_awake.ps1"), '-Sentinel', $sentinel
Add-Content -Path (Join-Path $root $c.status) -Value "$(Get-Date -Format o) RESUMED via resume_chain.ps1"
$argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $root $c.script), '-Sentinel', $sentinel)
if ($Only) { $argList += @('-Only', $Only) }
$p = Start-Process powershell -WindowStyle Hidden -PassThru -ArgumentList $argList
Write-Output "Chain '$Chain' resumed (pid $($p.Id)); progress in $($c.status)"
