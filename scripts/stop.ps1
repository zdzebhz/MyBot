[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Pids = Join-Path $Root ".data\pids"

$ExpectedExecutables = @{
    radar = Join-Path $Root ".venv\Scripts\python.exe"
    qwenpaw = Join-Path $Root ".runtime\qwenpaw\Scripts\qwenpaw.exe"
    openbiliclaw = Join-Path $Root ".runtime\openbiliclaw\.venv\Scripts\openbiliclaw.exe"
    ollama = Join-Path $Root ".runtime\ollama\bin\ollama.exe"
}
foreach ($Name in @("radar", "qwenpaw", "openbiliclaw", "ollama")) {
    $PidFile = Join-Path $Pids "$Name.pid"
    if (-not (Test-Path -LiteralPath $PidFile)) {
        Write-Host "[--] $Name 没有 PID 记录"
        continue
    }
    $RawPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($RawPid -match "^\d+$") {
        $Process = Get-Process -Id ([int]$RawPid) -ErrorAction SilentlyContinue
        if ($null -ne $Process) {
            $ExpectedPath = [IO.Path]::GetFullPath($ExpectedExecutables[$Name])
            $ActualPath = $Process.Path
            $ExpectedName = [IO.Path]::GetFileNameWithoutExtension($ExpectedPath)
            $PathMatches = (-not [string]::IsNullOrWhiteSpace($ActualPath)) -and
                [string]::Equals($ActualPath, $ExpectedPath, [StringComparison]::OrdinalIgnoreCase)
            $NameMatches = [string]::Equals($Process.ProcessName, $ExpectedName, [StringComparison]::OrdinalIgnoreCase)
            $OwnedProcess = $PathMatches -or $NameMatches
            if ($Name -eq "radar") {
                $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $RawPid"
                $OwnedProcess = $PathMatches -and ($ProcessInfo.CommandLine -match "-m\s+mybot\s+run")
            }
            if (-not $OwnedProcess) {
                Write-Warning "Stale PID file for $Name; refusing to stop PID $RawPid."
                Remove-Item -LiteralPath $PidFile -Force
                continue
            }
            & taskkill.exe /PID $Process.Id /T /F | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "无法停止 $Name 进程树（PID $($Process.Id)）。"
            }
            Write-Host "[OK] 已停止 $Name（PID $($Process.Id)）"
        }
    }
    Remove-Item -LiteralPath $PidFile -Force
}
