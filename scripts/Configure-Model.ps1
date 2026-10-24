[CmdletBinding()]
param([string]$Weights = '', [string]$Name = 'traffic-custom.pt')
. (Join-Path $PSScriptRoot 'Common.ps1')
Set-Location $ProjectRoot
$Python = Get-VenvPython
Write-Warning 'Only load trusted PyTorch checkpoints. A class-schema match does not prove accuracy.'
$Arguments = @('scripts\configure_model.py', '--name', $Name)
if ($Weights) { $Arguments += @('--weights', $Weights) }
Invoke-Checked $Python $Arguments
