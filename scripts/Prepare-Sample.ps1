[CmdletBinding()]
param([switch]$Force)
. (Join-Path $PSScriptRoot 'Common.ps1')
Set-Location $ProjectRoot
$Python = Get-VenvPython
$Arguments = @('scripts\prepare_sample.py')
if ($Force) { $Arguments += '--force' }
Invoke-Checked $Python $Arguments
