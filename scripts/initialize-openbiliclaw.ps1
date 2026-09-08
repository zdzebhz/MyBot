[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArguments = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OpenBiliRoot = Join-Path $Root ".runtime\openbiliclaw"
$OpenBiliExe = Join-Path $OpenBiliRoot ".venv\Scripts\openbiliclaw.exe"
$MyBotPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $OpenBiliExe)) {
    throw "OpenBiliClaw 未安装。请先运行 scripts\setup.ps1。"
}

$env:PYTHONUTF8 = "1"
Push-Location $OpenBiliRoot
try {
    $InitArgs = @("init")
    if ($ExtraArguments.Count -gt 0) {
        $InitArgs += $ExtraArguments
    }
    else {
        $InitArgs += @(
            "--yes-xhs", "--no-douyin", "--no-youtube", "--no-x",
            "--no-zhihu", "--no-reddit", "--no-linuxdo", "--no-v2ex",
            "--no-weibo", "--no-bangumi", "--no-github"
        )
    }
    Write-Host "即将进入 OpenBiliClaw 交互式初始化。"
    Write-Host "请按提示配置模型；浏览器需已登录 B 站和小红书。"
    & $OpenBiliExe @InitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "OpenBiliClaw 初始化失败（退出码 $LASTEXITCODE）。"
    }
}
finally {
    Pop-Location
}

Write-Host "[OK] OpenBiliClaw 初始化命令已完成"
& $MyBotPython -m mybot doctor
