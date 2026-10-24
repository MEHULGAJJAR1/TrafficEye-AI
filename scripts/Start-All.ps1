[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$BackendPort = 8000, [ValidateRange(1024,65535)][int]$FrontendPort = 5173)
. (Join-Path $PSScriptRoot 'Common.ps1')
Set-Location $ProjectRoot
$null = Get-VenvPython
Assert-FreePort $BackendPort
Assert-FreePort $FrontendPort
$Shell = if ($PSVersionTable.PSEdition -eq 'Core') { (Get-Command pwsh).Source } else { (Get-Command powershell.exe).Source }
$BackendScript = Join-Path $PSScriptRoot 'Start-Backend.ps1'
$FrontendScript = Join-Path $PSScriptRoot 'Start-Frontend.ps1'
# Start-Process joins arguments; quote full -File paths explicitly for folders containing spaces.
$Backend = Start-Process -FilePath $Shell -WorkingDirectory $ProjectRoot -ArgumentList @('-NoExit','-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $BackendScript + '"'),'-Port',"$BackendPort") -PassThru
$Frontend = Start-Process -FilePath $Shell -WorkingDirectory $ProjectRoot -ArgumentList @('-NoExit','-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $FrontendScript + '"'),'-Port',"$FrontendPort",'-BackendPort',"$BackendPort") -PassThru
Write-Host "Started backend terminal PID $($Backend.Id) and frontend terminal PID $($Frontend.Id)." -ForegroundColor Green
Write-Host "Open http://localhost:$FrontendPort after the services print that they are ready."
Write-Host 'Stop with Ctrl+C in each service window, then close the windows.'
Write-Host 'Unlock key command: Get-Content .\data\access.key'
