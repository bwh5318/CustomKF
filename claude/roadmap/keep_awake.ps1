# Holds a keep-awake request (ES_CONTINUOUS | ES_SYSTEM_REQUIRED) while the sentinel file exists.
# Blocks idle sleep only; an explicit sleep/hibernate request still suspends the machine. Changes no settings.
param([Parameter(Mandatory = $true)][string]$Sentinel)
$signature = '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
$api = Add-Type -MemberDefinition $signature -Name KeepAwake -Namespace Roadmap -PassThru
[void]$api::SetThreadExecutionState([uint32]"0x80000001")
Write-Output "keep-awake request active (pid $PID) while $Sentinel exists"
while (Test-Path -LiteralPath $Sentinel) { Start-Sleep -Seconds 30 }
Write-Output "keep-awake released"
