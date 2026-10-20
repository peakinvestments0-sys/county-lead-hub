param([switch]$Install)
$ErrorActionPreference = 'Stop'
$taskName = 'Florida Lead Hub'
$workspace = Split-Path -Parent $PSScriptRoot
$supervisor = Join-Path $PSScriptRoot 'lead_hub_supervisor.py'
$pythonPath = (Get-Command python.exe).Source
$pythonWindowless = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($Install -or -not $existing) {
    $userName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute $pythonWindowless -Argument ('"' + $supervisor + '"') -WorkingDirectory $workspace
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $userName
    $principal = New-ScheduledTaskPrincipal -UserId $userName -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Runs Lead Hub independently of terminals and restarts it if it exits.' -Force | Out-Null
}
Start-ScheduledTask -TaskName $taskName
Write-Output 'Lead Hub background task started. It also starts automatically at Windows sign-in.'
