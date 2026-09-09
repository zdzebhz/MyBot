[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

function Test-Url([string]$Name, [string]$Url) {
    try {
        $Response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
        Write-Host "[OK] $Name HTTP $($Response.StatusCode): $Url"
    }
    catch {
        Write-Host "[!!] $Name 未就绪: $Url"
    }
}

Test-Url "OpenBiliClaw" "http://127.0.0.1:8420/api/health"
Test-Url "QwenPaw" "http://127.0.0.1:8088/"
if (Test-Path -LiteralPath $Python) {
    & $Python -m mybot doctor
}
else {
    Write-Host "[!!] MyBot 未安装。请先运行 scripts\setup.ps1。"
}
