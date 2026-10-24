[CmdletBinding()]
param([switch]$Browser)
. (Join-Path $PSScriptRoot 'Common.ps1')
Set-Location $ProjectRoot
$Python = Get-VenvPython
Invoke-Checked $Python @('-m', 'pytest', '-q', '--cov=backend/app', '--cov-report=term-missing')
Push-Location (Join-Path $ProjectRoot 'frontend')
try {
    Invoke-Checked 'npm.cmd' @('test')
    Invoke-Checked 'npm.cmd' @('run', 'build')
    if ($Browser) {
        Write-Host 'Browser E2E expects both services running on ports 8000 / 5173 and a generated local key.'
        Invoke-Checked 'npx.cmd' @('playwright', 'install', 'chromium')
        Invoke-Checked 'npm.cmd' @('run', 'test:e2e')
    }
} finally { Pop-Location }
