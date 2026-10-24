[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port = 8000, [string]$BindHost = '127.0.0.1')
. (Join-Path $PSScriptRoot 'Common.ps1')
Set-Location $ProjectRoot
$Python = Get-VenvPython
Assert-FreePort $Port
Write-Host "TrafficEye API: http://localhost:$Port/api/health" -ForegroundColor Cyan
Write-Host "API documentation: http://localhost:$Port/api/docs"
Write-Host 'One worker only. Do not start multiple Uvicorn workers against this local queue.'
Write-Host 'Press Ctrl+C to stop gracefully; results are retained.'
Invoke-Checked $Python @('-m', 'uvicorn', 'backend.app.main:app', '--host', $BindHost, '--port', "$Port", '--workers', '1')
