[CmdletBinding()]
param(
    [ValidateSet('Cpu', 'Existing')][string]$TorchMode = 'Cpu',
    [string]$PythonCommand = 'python',
    [string]$ModelWeights = '',
    [switch]$SkipFrontend
)
. (Join-Path $PSScriptRoot 'Common.ps1')
Set-Location $ProjectRoot
Write-Host 'TrafficEye AI - Windows local setup' -ForegroundColor Cyan
Write-Host 'Install 64-bit Python 3.11-3.13 and Node.js 22 LTS (or Node 20.19+) first.'
Assert-Command $PythonCommand 'Install Python from https://www.python.org/downloads/windows/ and enable Add Python to PATH.'
Invoke-Checked $PythonCommand @('-c', "import sys,struct; assert (3,11)<=sys.version_info[:2]<=(3,13), 'Use Python 3.11-3.13'; assert struct.calcsize('P')==8, 'Use 64-bit Python'; print(sys.version)")
if (-not (Test-Path (Join-Path $ProjectRoot '.venv\Scripts\python.exe'))) {
    Invoke-Checked $PythonCommand @('-m', 'venv', '.venv')
}
$Python = Get-VenvPython
Invoke-Checked $Python @('-m', 'pip', 'install', '--upgrade', 'pip')
if ($TorchMode -eq 'Cpu') {
    Write-Host 'Installing matching CPU PyTorch wheels (no NVIDIA GPU required)...' -ForegroundColor Cyan
    Invoke-Checked $Python @('-m', 'pip', 'install', 'torch==2.9.1', 'torchvision==0.24.1', '--index-url', 'https://download.pytorch.org/whl/cpu')
} else {
    Write-Host 'Using existing PyTorch. Install compatible wheels into .venv using the official PyTorch selector before choosing this mode.'
    Invoke-Checked $Python @('-c', "import torch,torchvision; print(torch.__version__, torchvision.__version__); assert torch.__version__.split('+')[0]=='2.9.1', 'Expected torch 2.9.1'; assert torchvision.__version__.split('+')[0]=='0.24.1', 'Expected torchvision 0.24.1'")
}
Invoke-Checked $Python @('-m', 'pip', 'install', '-r', 'requirements-dev.txt')
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
Invoke-Checked $Python @('scripts\init_workspace.py', '--check-imports')
Invoke-Checked $Python @('scripts\prepare_sample.py')
if ($ModelWeights) {
    Write-Warning 'Loading .pt checkpoints can execute code. Only configure weights you trust.'
    & $Python 'scripts\configure_model.py' '--weights' $ModelWeights
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Model is not ready. Read the message above; the explicitly labelled synthetic demo remains functional.' }
}
if (-not $SkipFrontend) {
    Assert-Command 'node' 'Install Node.js 22 LTS from https://nodejs.org/ and reopen PowerShell.'
    Assert-Command 'npm.cmd' 'npm is supplied with Node.js. Reopen PowerShell after installation.'
    Invoke-Checked 'node' @('-e', "let [m,n]=process.versions.node.split('.').map(Number); if(m<20 || m>24 || (m===20 && n<19)) { console.error('Use Node 20.19+ or 22/24 LTS'); process.exit(1) }")
    Push-Location (Join-Path $ProjectRoot 'frontend')
    try { Invoke-Checked 'npm.cmd' @('ci', '--no-audit', '--no-fund'); Invoke-Checked 'npm.cmd' @('run', 'build') }
    finally { Pop-Location }
}
Write-Host ''
Write-Host 'Setup complete. No trained custom traffic weights are bundled.' -ForegroundColor Green
Write-Host 'Next: .\scripts\Start-All.ps1'
Write-Host 'Frontend: http://localhost:5173    API: http://localhost:8000/api/health'
Write-Host 'Unlock key: Get-Content .\data\access.key  (unless TE_API_KEY is set in .env)'
Write-Host 'Try: Video workspace > Import synthetic sample > Start processing.'
