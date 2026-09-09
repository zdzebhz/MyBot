[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Data = Join-Path $Root ".data"
$Logs = Join-Path $Data "logs"
$Pids = Join-Path $Data "pids"
$OpenBiliRoot = Join-Path $Root ".runtime\openbiliclaw"
$OpenBiliExe = Join-Path $OpenBiliRoot ".venv\Scripts\openbiliclaw.exe"
$QwenExe = Join-Path $Root ".runtime\qwenpaw\Scripts\qwenpaw.exe"
$QwenConfig = Join-Path $Data "qwenpaw\config.json"

foreach ($Required in @($OpenBiliExe, $QwenExe)) {
    if (-not (Test-Path -LiteralPath $Required)) {
        throw "缺少 $Required。请先运行 scripts\setup.ps1。"
    }
}
if (-not (Test-Path -LiteralPath $QwenConfig)) {
    throw "QwenPaw is not initialized. Run setup.ps1 with -AcceptQwenPawSecurityNotice."
}

New-Item -ItemType Directory -Force -Path $Logs, $Pids | Out-Null

$env:QWENPAW_WORKING_DIR = Join-Path $Data "qwenpaw"
$env:MYBOT_ROOT = $Root
$env:PYTHONUTF8 = "1"

function Get-TrackedProcess([string]$PidFile) {
    if (-not (Test-Path -LiteralPath $PidFile)) {
        return $null
    }
    $RawPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($RawPid -notmatch "^\d+$") {
        return $null
    }
    return Get-Process -Id ([int]$RawPid) -ErrorAction SilentlyContinue
}

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$Executable,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    $PidFile = Join-Path $Pids "$Name.pid"
    $Existing = Get-TrackedProcess $PidFile
    if ($null -ne $Existing) {
        Write-Host "[OK] $Name 已在运行（PID $($Existing.Id)）"
        return
    }
    $StartArgs = @{
        FilePath = $Executable
        ArgumentList = $Arguments
        WorkingDirectory = $WorkingDirectory
        WindowStyle = "Hidden"
        RedirectStandardOutput = (Join-Path $Logs "$Name.out.log")
        RedirectStandardError = (Join-Path $Logs "$Name.err.log")
        PassThru = $true
    }
    $Process = Start-Process @StartArgs
    Set-Content -LiteralPath $PidFile -Value $Process.Id -Encoding ascii
    Write-Host "[OK] 已启动 $Name（PID $($Process.Id)）"
}

$OpenBiliArgs = @{
    Name = "openbiliclaw"
    Executable = $OpenBiliExe
    Arguments = @("start", "--host", "127.0.0.1", "--port", "8420")
    WorkingDirectory = $OpenBiliRoot
}
$QwenArgs = @{
    Name = "qwenpaw"
    Executable = $QwenExe
    Arguments = @("app")
    WorkingDirectory = $Root
}
Start-ManagedProcess @OpenBiliArgs
Start-ManagedProcess @QwenArgs

Start-Sleep -Seconds 4
Write-Host ""
Write-Host "OpenBiliClaw: http://127.0.0.1:8420/"
Write-Host "QwenPaw:      http://127.0.0.1:8088/"
Write-Host "日志目录:     $Logs"
