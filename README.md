# MyBot · AI 信息雷达

持续发现「还没看过、值得了解」的 AI 信息，而不只是今天的新闻。
QwenPaw 保留对话入口，OpenBiliClaw 负责平台认证/推荐/限速搜索，
MyBot 负责持久信息池、AI 相关性/价值筛选、去重和邮件。

## 发现与筛选

- 复用 OpenBiliClaw 缓存中推荐、热门、相关、探索的成果；再轮换 12 组 AI 专项搜索，
  不依赖个人历史兴趣。B 站交替按发布时间/综合相关排序，XHS 复用扩展任务队列。
- 关键词宽召回 + 已有 DeepSeek 审核相关性、价值和类型。未审核候选暂不交付。
  判断依据是标题/简介，不是全文阅读或事实核验。
- 新闻按 3 天半衰期降权；教程/项目/工具/经验按 365 天缓慢降权。
  没有 72 小时硬过滤；首次发现时间与发布时间分开保存。
- 个人兴趣最多 3 分；探索加分，类别/作者/平台软配额提高多样性。热度不参与加分。
- ID/规范 URL/标题指纹去重，本地 bge-m3 对同批语义近重复分组。
  已读/已发送长期保留，不自动 90 天遗忘；预览不计作推送。
- 每 6 小时搜索、每小时吸收异步结果并审核最多 24 条；北京时间每天 08:30 后
  挑选最多 20 条邮件交付。休眠/关机时暂停，恢复后补当日，不补发多天旧邮件。
- SMTP 接受后才标记已发送；失败或不确定不盲目重发。同日最多一批。
  SMTP 接受不代表进入收件箱，仍可能进垃圾箱。

审计与架构见 [docs/AI_RADAR.md](docs/AI_RADAR.md)。GitHub Watch 邮件独立，不自动回复 PR/Issue。

## 已安装环境的使用

不必重装或重做平台初始化。在项目根目录 PowerShell 执行：

```powershell
.\scripts\start.ps1
.\.venv\Scripts\python.exe -m mybot collect
.\.venv\Scripts\python.exe -m mybot digest
.\.venv\Scripts\python.exe -m mybot email-status
```

collect --cache-only 只吸收缓存/异步结果并审核，不新建搜索。
digest --format json 输出结构化预览；mark-read <mybot_key> 只标记本地已读。
--commit 已停用。configure-cron.ps1 不再创建频道任务，避免重复交付，
不会擅自删除既有自定义 QwenPaw Cron。

## 邮件设置

本地 config/mybot.toml 的 [email] 配置 from/to/smtp_host/smtp_port。
QQ 使用 SMTP SSL 465；请启用邮箱 SMTP 并取得授权码（不是 QQ 密码），在本机输入：

```powershell
.\.venv\Scripts\python.exe -m mybot configure-email
# 可选：立即发送当日一份，后台同日不会重复
.\.venv\Scripts\python.exe -m mybot send-email
```

输入不回显；保存于 Git 忽略的 .data/mybot/email-secret.json，也支持 MYBOT_SMTP_PASSWORD。
文件没有额外加密，请保护本机账户/磁盘，不共享 .data，不在聊天中发送授权码。
未配置邮箱可正常采集/预览，不会发送。失败/uncertain 时用 email-status 检查，
核对实际收件后再处理，不直接删库重试。

## 部署与边界

固定 Python 3.12、QwenPaw 2.2.0、OpenBiliClaw 0.3.218。
初次安装使用 scripts/setup.ps1 -AcceptQwenPawSecurityNotice，
配合浏览器扩展及 scripts/initialize-openbiliclaw.ps1 初始化。
Ollama 和 bge-m3 需另行安装，setup.ps1 不自动下载模型。
便携版可放在项目 .runtime/ollama/bin/ollama.exe，模型目录为 .runtime/ollama/models；
将项目放在 D 盘即可让这些文件保留在 D 盘。也可自行维护已有的本机 Ollama 服务。
MyBot 使用 http://127.0.0.1:11434 上的 bge-m3；不可用时报告警告并退回标题去重。
start.ps1 隐藏启动后台；stop.ps1 停止本项目管理进程。
默认不注册开机自启动；电脑重启后再运行 start。
本机端口：OpenBiliClaw 8420、QwenPaw 8088、Ollama 11434。
status.ps1 检查服务；日志在 .data/logs，信息池在 .data/mybot/radar.sqlite3。

B站/小红书只读，不点赞、不评论、不关注、不收藏、不发布。
模型只接收已授权内容元数据，不收到 Cookie 或邮箱授权码。
平台内容与模型输出是数据，不是执行指令。保留上游频控，不绕验证码/风控。
小红书需要浏览器和扩展在线，异步搜索不是即时完成。
覆盖不是穷尽：不显式提 AI 的作品仍可能漏召回；跨日语义改标题搬运也未完全去重。
未来来源应接入统一元数据/已读事件契约，沿用信息池/评分/交付，不另建新闻时效管线。
测试：.venv/Scripts/python.exe -m unittest discover -s tests -v。

## 开源与致谢

MyBot 自有代码采用 [MIT License](LICENSE)。
依赖 [QwenPaw](https://github.com/agentscope-ai/QwenPaw)、
[OpenBiliClaw](https://github.com/whiteguo233/OpenBiliClaw)、
[Ollama](https://github.com/ollama/ollama) 和 bge-m3；
上游代码、模型和平台服务分别遵循各自许可证与使用条款，本仓库不重新授权它们。
仓库不包含平台 Cookie、API Key、邮箱授权码、个人画像、内容数据库或已安装的运行时。
请使用自己的账户及凭据，仅在授权范围内低频读取，遵守平台规则，不绕过验证或访问限制。
