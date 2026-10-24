[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port = 5173, [ValidateRange(1024,65535)][int]$BackendPort = 8000, [string]$BindHost = '127.0.0.1', [switch]$ProductionPreview)
. (Join-Path $PSScriptRoot 'Common.ps1')
Assert-Command 'npm.cmd' 'Install Node.js 22 LTS and reopen PowerShell.'
if (-not (Test-Path (Join-Path $ProjectRoot 'frontend\node_modules'))) { throw 'Frontend dependencies are missing. Run .\scripts\Setup.ps1.' }
Assert-FreePort $Port
$env:TE_BACKEND_URL = "http://127.0.0.1:$BackendPort"
Set-Location (Join-Path $ProjectRoot 'frontend')
Write-Host "TrafficEye dashboard: http://localhost:$Port" -ForegroundColor Cyan
Write-Host "API proxy: relative /api -> $env:TE_BACKEND_URL"
Write-Host 'Use the key from data/access.key in the project root to unlock the dashboard.'
if ($ProductionPreview) {
    Invoke-Checked 'npm.cmd' @('run', 'build')
    Invoke-Checked 'npm.cmd' @('run', 'preview', '--', '--host', $BindHost, '--port', "$Port")
} else {
    Invoke-Checked 'npm.cmd' @('run', 'dev', '--', '--host', $BindHost, '--port', "$Port")
}
