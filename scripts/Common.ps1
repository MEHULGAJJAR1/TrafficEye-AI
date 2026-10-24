Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Assert-Command([string]$Name, [string]$HelpText) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "$Name was not found. $HelpText" }
}
function Invoke-Checked {
    param([Parameter(Mandatory=$true)][string]$FilePath, [string[]]$Arguments = @())
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $FilePath $($Arguments -join ' ')" }
}
function Get-VenvPython {
    $PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $PythonPath)) { throw 'Virtual environment not found. Run .\scripts\Setup.ps1 first.' }
    return $PythonPath
}
function Assert-FreePort([int]$Port) {
    $Listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try { $Listener.Start() }
    catch { throw "Port $Port is occupied. Stop the existing process or use another port in both launchers/proxy settings." }
    finally { $Listener.Stop() }
}
