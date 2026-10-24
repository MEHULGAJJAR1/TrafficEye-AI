. (Join-Path $PSScriptRoot 'Common.ps1')
Set-Location $ProjectRoot
$Python = Get-VenvPython
Invoke-Checked $Python @('scripts\doctor.py')
Write-Host 'Ports (if occupied):'
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
