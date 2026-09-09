# MyBot

一个本地优先、只读的个人 AI 资讯助理。当前版本以
[QwenPaw](https://github.com/agentscope-ai/QwenPaw) 作为 Agent OS 和消息频道，
以 [OpenBiliClaw](https://github.com/whiteguo233/OpenBiliClaw) 发现 B 站、
小红书内容，MyBot 负责 AI 主题过滤、时效排序、去重和日报格式。

## 当前能力

- 从 B 站、小红书的 OpenBiliClaw 推荐池读取内容。
- 只保留最近 72 小时且命中 AI 关键词的条目。
- 跨平台去重；已推送内容在 90 天内不重复发送。
- 一个平台暂时失败时，仍输出另一个平台的结果并标注失败原因。
- 通过 QwenPaw 接入 QQ、飞书、钉钉、Discord 等受支持频道。
- 用 QwenPaw Cron 每天定时生成并推送中文摘要。
- 提供 `doctor`、启动、停止、状态检查和定时配置脚本。

GitHub 邮件提醒继续使用 GitHub 自带的 Watch/Notifications 设置，已经与本项目
解耦。本仓库不会自动回复 PR、Issue 或 Review。

## 安全边界

本版本严格只读：

- 不点赞、不评论、不关注、不收藏、不发帖。
- 不提供 GitHub 自动回复。
- 平台内容始终被当作不可信数据，而不是 Agent 指令。
- Cookie、Token、API Key 和本地状态只放在被 Git 忽略的
  `.runtime/`、`.data/`、`config/mybot.toml` 中。
- 服务默认只监听本机回环地址，不直接暴露到局域网或公网。

## 固定版本

- Python 3.12
- QwenPaw 2.2.0
- OpenBiliClaw 0.3.218

上游仍在快速迭代，尤其 OpenBiliClaw 标记为 Pre-Alpha。本项目固定版本是为了
让首版可复现；升级前应先跑测试和 `doctor`。

## 快速开始（Windows）

以下命令使用 Windows 自带的 `powershell.exe`，因此兼容 Windows PowerShell 5.1。
PowerShell 7 用户也可以将命令开头替换为 `pwsh`。

### 1. 安装

先阅读 QwenPaw 首次初始化显示的安全说明；确认接受后，在仓库根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -AcceptQwenPawSecurityNotice
```

脚本会创建项目虚拟环境、安装固定版本的两个上游、生成本地配置，并把
`ai-daily-digest` Skill 安装到项目专属的 QwenPaw 工作区。

MyBot 默认替你关闭 QwenPaw 的匿名环境遥测。若你愿意开启，可额外传入
`-EnableQwenPawTelemetry`。

### 2. 启动本地服务

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

打开：

- QwenPaw 控制台：<http://127.0.0.1:8088/>
- OpenBiliClaw：<http://127.0.0.1:8420/>

两个进程都以隐藏窗口运行，日志写入 `.data/logs/`。

### 3. 登录 B 站和小红书并初始化画像

1. 从 [OpenBiliClaw Releases](https://github.com/whiteguo233/OpenBiliClaw/releases)
   下载与固定版本匹配的 Chrome/Edge 浏览器扩展并加载。
2. 在同一个浏览器中分别登录 B 站和小红书，保持浏览器与扩展开启。
3. 运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\initialize-openbiliclaw.ps1
```

脚本默认只启用 B 站和小红书，显式关闭其他内容源。初始化会交互式询问 OpenBiliClaw
使用的模型服务、模型名和 API Key；请本人填写。验证码、扫码登录和风控验证也
必须本人完成。任何凭据都不要提交到 Git。

### 4. 配置 QwenPaw 模型和消息频道

进入 QwenPaw 控制台：

1. 在“设置 → 模型”中添加你要使用的模型和 API Key。
2. 在“控制 → 频道”中启用 QQ、飞书或其他目标频道。
3. 按页面说明完成 Bot 凭据、用户白名单及会话配对。

频道涉及外部平台账号，MyBot 不会替你创建或授权账号。

### 5. 试跑日报

预览不会写入已推送账本：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\digest.ps1
```

查看原始 JSON：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\digest.ps1 -Format json
```

确认内容正常后，可在 QwenPaw 对话中发送“生成今天的 AI 日报”，或直接使用
`/ai-daily-digest`。

### 6. 创建每日推送

先从已经配对成功的 QwenPaw 会话中取得频道、用户 ID 和会话 ID，然后运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\configure-cron.ps1 `
  -Channel "qq" `
  -TargetUser "你的用户ID" `
  -TargetSession "你的会话ID"
```

默认每天 08:30（Asia/Shanghai）推送。自定义时间示例：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\configure-cron.ps1 `
  -Channel "feishu" `
  -TargetUser "ou_xxx" `
  -TargetSession "oc_xxx" `
  -Cron "0 9 * * *"
```

## 常用命令

```powershell
# 完整环境与桥接检查
.\scripts\status.ps1

# 刷新推荐池后预览（比默认模式慢）
.\scripts\digest.ps1 -Refresh

# 输出并写入去重账本，通常只给定时任务使用
.\scripts\digest.ps1 -Format json -Commit

# 停止本项目启动的两个后台进程
.\scripts\stop.ps1
```

直接使用 Python CLI：

```powershell
.\.venv\Scripts\python.exe -m mybot doctor
.\.venv\Scripts\python.exe -m mybot digest --format markdown
```

## 调整信息范围

首次安装后编辑 `config/mybot.toml`：

- `platforms`：采集平台。
- `fetch_per_platform`：每个平台候选数。
- `digest_limit`：日报最多条目数。
- `max_age_hours`：内容最大年龄。
- `keywords`：AI 关键词；匹配时不区分大小写。

本地配置不会被 Git 跟踪。模板见
[config/mybot.example.toml](config/mybot.example.toml)。

## 工作原理

```text
B站 / 小红书登录态
        ↓（浏览器扩展）
OpenBiliClaw 推荐池
        ↓（只读 Agent Bridge）
MyBot：时效过滤 → AI 评分 → 去重 → JSON/Markdown
        ↓
QwenPaw Skill + Cron
        ↓
QQ / 飞书 / 其他已配置频道
```

## 故障排查

- `doctor` 提示 OpenBiliClaw 不可用：先确认安装和初始化完成。
- 小红书为 0 条：确认浏览器已登录、扩展已启用且本地后端在运行；若出现验证码，
  请在浏览器中本人完成。
- QwenPaw 没有发送：确认模型调用成功、频道已配对、目标用户/会话 ID 正确，
  再用 QwenPaw 的 `cron list` 和 `cron run` 检查任务。
- 日报为空：可先用 `-Refresh`，再按需要扩大
  `max_age_hours` 或补充关键词。
- 查看 `.data/logs/openbiliclaw.err.log` 与
  `.data/logs/qwenpaw.err.log` 获取后台错误。

架构选择的完整比较仍保存在
[docs/ARCHITECTURE_OPTIONS.md](docs/ARCHITECTURE_OPTIONS.md)。
