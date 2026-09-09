[CmdletBinding()]
param(
    [switch]$SkipDependencyInstall,
    [switch]$AcceptQwenPawSecurityNotice,
    [switch]$EnableQwenPawTelemetry
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Runtime = Join-Path $Root ".runtime"
$Data = Join-Path $Root ".data"
$MyBotPython = Join-Path $Root ".venv\Scripts\python.exe"
$QwenPython = Join-Path $Runtime "qwenpaw\Scripts\python.exe"
$QwenExe = Join-Path $Runtime "qwenpaw\Scripts\qwenpaw.exe"
$OpenBiliRoot = Join-Path $Runtime "openbiliclaw"
$QwenData = Join-Path $Data "qwenpaw"
$QwenConfig = Join-Path $QwenData "config.json"

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "缺少命令 '$Name'。请先安装后重新运行。"
    }
}

function Invoke-Checked {
    param([string]$FilePath, [string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "命令失败（$LASTEXITCODE）：$FilePath $($Arguments -join ' ')"
    }
}

Require-Command "uv"
Require-Command "git"
New-Item -ItemType Directory -Force -Path $Runtime, $Data | Out-Null

$LocalConfig = Join-Path $Root "config\mybot.toml"
if (-not (Test-Path -LiteralPath $LocalConfig)) {
    $ExampleConfig = Join-Path $Root "config\mybot.example.toml"
    Copy-Item -LiteralPath $ExampleConfig -Destination $LocalConfig
    Write-Host "[OK] 已创建本地配置 config\mybot.toml"
}

if (-not $SkipDependencyInstall) {
    if (-not (Test-Path -LiteralPath $MyBotPython)) {
        Invoke-Checked "uv" @(
            "venv", (Join-Path $Root ".venv"), "--python", "3.12"
        )
    }
    Invoke-Checked "uv" @(
        "pip", "install", "--python", $MyBotPython, "--editable", $Root
    )
    Write-Host "[OK] MyBot 已安装到项目虚拟环境"

    if (-not (Test-Path -LiteralPath $QwenPython)) {
        Invoke-Checked "uv" @(
            "venv", (Join-Path $Runtime "qwenpaw"), "--python", "3.12"
        )
    }
    Invoke-Checked "uv" @(
        "pip", "install", "--python", $QwenPython, "qwenpaw==2.2.0"
    )
    Write-Host "[OK] QwenPaw 2.2.0 已安装"

    if (-not (Test-Path -LiteralPath $OpenBiliRoot)) {
        Invoke-Checked "git" @(
            "clone", "--depth", "1", "--branch", "openbiliclaw-v0.3.218",
            "https://github.com/whiteguo233/OpenBiliClaw.git", $OpenBiliRoot
        )
    }
    Push-Location $OpenBiliRoot
    try {
        Invoke-Checked "uv" @("sync", "--extra", "browser", "--frozen")
    }
    finally {
        Pop-Location
    }
    Write-Host "[OK] OpenBiliClaw 0.3.218 已安装"
}

if (-not (Test-Path -LiteralPath $QwenExe)) {
    throw "QwenPaw 尚未安装。请去掉 -SkipDependencyInstall 后重试。"
}

$env:QWENPAW_WORKING_DIR = $QwenData
$env:MYBOT_ROOT = $Root
$env:PYTHONUTF8 = "1"

if (-not $EnableQwenPawTelemetry -and
    -not (Test-Path -LiteralPath $QwenConfig)) {
    New-Item -ItemType Directory -Force -Path $QwenData | Out-Null
    $TelemetryMarker = Join-Path $QwenData ".telemetry_collected"
    $TelemetryData = [ordered]@{
        collected_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        qwenpaw_version = "2.2.0"
        collected_versions = @("2.2.0")
        opted_out = $true
        version = "1.3"
    }
    $TelemetryJson = $TelemetryData | ConvertTo-Json -Compress
    [IO.File]::WriteAllText(
        $TelemetryMarker,
        $TelemetryJson,
        [Text.UTF8Encoding]::new($false)
    )
}

if (-not (Test-Path -LiteralPath $QwenConfig)) {
    if ($AcceptQwenPawSecurityNotice) {
        Invoke-Checked $QwenExe @(
            "init", "--defaults", "--accept-security"
        )
        Write-Host "[OK] QwenPaw 本地工作目录已初始化"
    }
    else {
        Write-Warning (
            "QwenPaw 要求用户本人接受其安全提示。依赖已装好；" +
            "阅读 README 后使用 -AcceptQwenPawSecurityNotice 再运行本脚本。"
        )
    }
}

if (Test-Path -LiteralPath $QwenConfig) {
    $SkillTarget = Join-Path $QwenData (
        "workspaces\default\skills\ai-daily-digest"
    )
    New-Item -ItemType Directory -Force -Path $SkillTarget | Out-Null
    $SkillSource = Join-Path $Root "skills\ai-daily-digest\SKILL.md"
    Copy-Item -LiteralPath $SkillSource -Destination (
        Join-Path $SkillTarget "SKILL.md"
    ) -Force
    Invoke-Checked $QwenExe @(
        "skills", "enable", "ai-daily-digest", "--agent-id", "default"
    )
    Write-Host "[OK] ai-daily-digest Skill 已安装并启用"
}

if (Test-Path -LiteralPath $MyBotPython) {
    & $MyBotPython -m mybot doctor
    if ($LASTEXITCODE -ne 0) {
        Write-Warning (
            "依赖已安装，但账号/模型初始化尚未全部完成" +
            "（这是首次安装的预期状态）。"
        )
    }
}

Write-Host ""
Write-Host "下一步："
Write-Host "1. 运行 scripts\start.ps1，启动两个本地服务。"
Write-Host "2. 安装扩展、登录 B 站/小红书，再运行 initialize-openbiliclaw.ps1。"
Write-Host "3. 配置模型，在 config/mybot.toml 填写邮箱，然后运行 mybot configure-email。"
