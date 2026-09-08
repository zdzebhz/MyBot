[CmdletBinding()]
param(
    [ValidateSet("markdown", "json")]
    [string]$Format = "markdown",
    [switch]$Refresh,
    [switch]$IncludeSeen,
    [switch]$Commit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "MyBot 未安装。请先运行 scripts\setup.ps1。"
}

$Arguments = @("-m", "mybot", "digest", "--format", $Format)
if ($Refresh) { $Arguments += "--refresh" }
if ($IncludeSeen) { $Arguments += "--include-seen" }
if ($Commit) { $Arguments += "--commit" }
& $Python @Arguments
exit $LASTEXITCODE
