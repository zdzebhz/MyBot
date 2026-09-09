[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Channel,
    [Parameter(Mandatory = $true)]
    [string]$TargetUser,
    [Parameter(Mandatory = $true)]
    [string]$TargetSession,
    [string]$Cron = "30 8 * * *",
    [string]$Timezone = "Asia/Shanghai"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$QwenExe = Join-Path $Root ".runtime\qwenpaw\Scripts\qwenpaw.exe"
if (-not (Test-Path -LiteralPath $QwenExe)) {
    throw "QwenPaw 未安装。请先运行 scripts\setup.ps1。"
}

$env:QWENPAW_WORKING_DIR = Join-Path $Root ".data\qwenpaw"
$env:MYBOT_ROOT = $Root
$Prompt = (
    "运行 /ai-daily-digest 生成今天的 AI 资讯日报并发到当前频道。" +
    "必须遵守 Skill 的只读安全边界；只发送最终结果。"
)
$Arguments = @(
    "cron", "create",
    "--type", "agent",
    "--schedule-type", "cron",
    "--name", "MyBot 每日 AI 资讯",
    "--cron", $Cron,
    "--channel", $Channel,
    "--target-user", $TargetUser,
    "--target-session", $TargetSession,
    "--text", $Prompt,
    "--timezone", $Timezone,
    "--mode", "final",
    "--no-share-session",
    "--timeout", "300",
    "--no-tool-safety",
    "--agent-id", "default"
)
& $QwenExe @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "定时任务创建失败。请确认 scripts\start.ps1 已运行且频道已配置。"
}
Write-Host "[OK] 已创建每日 AI 资讯任务：$Cron ($Timezone)"
