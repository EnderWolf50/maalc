<#
Stop the bot and everything it spawned.

  pwsh tools/live/stop_run.ps1 [-RunPid <pid of the process that started the bot>] [-WhatIf]

The bot starts agent\main.py children that outlive a plain Stop-Process on their parent:
taskkill /T takes the whole tree of -RunPid, then every python still running agent\main.py is
stopped too. -WhatIf lists them without stopping anything.
#>
[CmdletBinding(SupportsShouldProcess)]
param([int]$RunPid)   # $PID is reserved in PowerShell

if ($RunPid -and $PSCmdlet.ShouldProcess("process tree of $RunPid", "taskkill /T /F")) {
    taskkill /T /F /PID $RunPid 2>$null | Out-Null
}
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'agent[\\/]main\.py' } |
    ForEach-Object {
        if ($PSCmdlet.ShouldProcess("python $($_.ProcessId): $($_.CommandLine)", "Stop-Process")) {
            Stop-Process -Id $_.ProcessId -Force
            "stopped $($_.ProcessId)"
        }
    }
