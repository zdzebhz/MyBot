[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Pids = Join-Path $Root ".data\pids"

$ExpectedExecutables = @{
    qwenpaw = Join-Path $Root ".runtime\qwenpaw\Scripts\qwenpaw.exe"
    openbiliclaw = Join-Path $Root ".runtime\openbiliclaw\.venv\Scripts\openbiliclaw.exe"
}
foreach ($Name in @("qwenpaw", "openbiliclaw")) {
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
            $OwnedProcess = (-not [string]::IsNullOrWhiteSpace($ActualPath)) -and
                [string]::Equals($ActualPath, $ExpectedPath, [StringComparison]::OrdinalIgnoreCase)
            if (-not $OwnedProcess) {
                Write-Warning "Stale PID file for $Name; refusing to stop PID $RawPid."
                Remove-Item -LiteralPath $PidFile -Force
                continue
            }
            Stop-Process -Id $Process.Id
            Write-Host "[OK] 已停止 $Name（PID $($Process.Id)）"
        }
    }
    Remove-Item -LiteralPath $PidFile -Force
}
