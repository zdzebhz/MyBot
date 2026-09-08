# MyBot 制作方案（待选型）

> **Status (2026-09-08): archived decision record.** The implemented design is
> QwenPaw + OpenBiliClaw + the read-only MyBot adapter. GitHub notifications use
> GitHub's native email settings, and automatic GitHub replies are intentionally
> out of scope. See the repository README for the current operating guide.


更新时间：2026-09-08

## 先解释截图里的现象

截图中的邮件主体是 GitHub 自带的通知邮件，并不意味着组长另写了“邮件机器人”。只要在 GitHub 中订阅了仓库或参与了 PR，并启用邮件通知，评论、关闭 PR、CI 失败等事件就可以由 GitHub 发到邮箱；直接回复这种邮件，还可以把回复作为评论发回对应的 PR/Issue。

`vercel[bot]` 是 GitHub App 身份。`wanyang63` 显示的是普通用户身份：它可能是本人手动操作，也可能是脚本使用该账号的令牌操作，仅凭截图无法判断。真正自建且希望显示为 `xxx[bot]`，通常应创建 GitHub App，而不是让一台个人电脑长期登录普通账号。

## 共同的产品边界

- GitHub：PR 新建/更新、Review、评论、CI 结果、指派和 @提及提醒；可配置自动确认回复。
- AI 日报：按关键词、账号白名单和发布时间抓取候选内容，进行去重、可信度标注、摘要和邮件推送。
- 第一版不允许模型自动批准、合并或关闭 PR；此类动作必须人工确认。
- 小红书当前公开开放能力重点并不是全站笔记搜索；B 站开放平台也不等于提供任意全站检索能力。若依赖网页自动化，必须接受登录状态、验证码、页面变更和平台规则带来的维护成本。

## 方案 A：GitHub 原生能力 + GitHub Actions 定时任务

### 组成

- GitHub 自带邮件通知负责大多数 GitHub 提醒。
- GitHub Actions 监听 PR 事件并通过 API 留下固定模板回复。
- 每日定时 Action 聚合允许访问的信息源，生成摘要并调用邮件服务发送。

### 优点

- 不需要电脑常开，也不需要先买服务器。
- 最快、最便宜，适合验证需求。
- 代码和运行记录都在 GitHub，容易维护。

### 局限

- 定时任务不是严格实时服务；高峰期可能延迟。
- 不适合需要登录态和浏览器操作的小红书采集。
- 复杂的 AI 审查、多仓库权限和状态存储会逐渐把工作流写得很重。

### 适合

先做 1～2 周 MVP，确认真正需要哪些提醒和日报栏目。

## 方案 B：GitHub App + 云端常驻/Serverless 服务（推荐）

### 组成

- 注册自己的 GitHub App，以 `MyBot[bot]` 身份安装到指定仓库。
- GitHub Webhook 实时触发云端服务；服务负责规则判断、自动评论和邮件发送。
- 云端定时任务收集官方 API、RSS、公开网页、搜索结果和白名单账号内容。
- 数据库存储事件、去重指纹、订阅规则与推送记录。

### 优点

- GitHub 事件实时，身份和权限边界清楚，不依赖个人电脑。
- 适合扩展到多个仓库、多人使用和可配置规则。
- Webhook 可重试、可审计，长期维护最正规。

### 局限

- 需要部署平台、域名/HTTPS、数据库和邮件服务。
- 小红书/B 站的非官方网页采集风险仍然存在，云机 IP 也可能更容易触发风控。
- 比方案 A 多一些初始工程量和少量云服务成本。

### 适合

希望长期使用，且 GitHub 自动化是核心功能。

## 方案 C：本机常驻个人 Agent + 浏览器自动化

### 组成

- Windows 上运行常驻服务或计划任务。
- 使用已登录的浏览器访问 B 站、小红书，模拟人工搜索、关注和筛选。
- GitHub 通过轮询通知 API，或使用公网隧道接收 Webhook。
- 本机调用模型生成摘要，再通过邮箱 SMTP/API 推送。

### 优点

- 最容易利用你已有的平台登录状态。
- 对没有正式搜索 API 的平台，内容覆盖潜力最高。
- 数据可以主要留在本机。

### 局限

- 电脑需要保持开机联网；休眠、更新或浏览器退出都会影响运行。
- 页面改版、验证码、Cookie 过期和反自动化机制会导致维护频繁。
- 必须限制访问频率，并核对平台协议；不适合大规模抓取。

### 适合

仅个人低频使用，而且“小红书最新内容覆盖”比稳定性更重要。

## 方案 D：云端 GitHub App + 本机社交采集器（混合方案）

### 组成

- GitHub 部分采用方案 B，保持实时和稳定。
- 社交平台部分采用本机低频浏览器采集。
- 两端统一将候选信息交给云端或本机摘要器，最后合并为一封日报。

### 优点

- GitHub 不受电脑开关机影响。
- 社交平台可以利用本机正常登录环境。
- 每部分都采用更适合它的运行位置。

### 局限

- 部署、认证、同步和故障排查最复杂。
- 需要维护云端与本机两套运行环境。

### 适合

在 MVP 已证明有价值后，作为最终形态逐步演进。

## 建议的决策

推荐先做“方案 A 的 MVP”，但代码结构按“方案 B”可迁移的方式组织：

1. 第一期只做 GitHub 邮件设置、PR 固定确认回复、每天一封 AI 日报。
2. 日报先接入稳定来源（官方博客、GitHub Trending/Release、arXiv、RSS、公开搜索）和指定的 B 站 UP 主。
3. 小红书先采用账号/关键词白名单的人工链接投递或低频本机采集实验，不承诺全站完整覆盖。
4. 当需要更实时、多仓库或更复杂回复时，把 GitHub 部分升级为方案 B。
5. 只有确认小红书覆盖确实重要，再加入方案 C 的本机采集器，演进为方案 D。

## 正式开发前需要确定

- GitHub 自动回复是固定确认语、规则模板，还是 AI 生成草稿。
- 需要覆盖个人仓库、组织仓库，还是二者都有。
- 收件邮箱及发信渠道（邮箱 SMTP、Resend、SendGrid 等）。
- AI 日报的关键词、指定账号、每天发送时间和期望篇数。
- 是否接受本机常开，以及是否接受浏览器自动化的维护与平台风控风险。

## 参考资料

- [GitHub：配置通知与用邮件回复](https://docs.github.com/en/subscriptions-and-notifications/get-started/configuring-notifications)
- [GitHub：使用 GitHub App Webhook](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/using-webhooks-with-github-apps)
- [GitHub：响应 Webhook 并评论 PR 的教程](https://docs.github.com/en/apps/creating-github-apps/writing-code-for-a-github-app/building-a-github-app-that-responds-to-webhook-events)
- [GitHub Actions：定时工作流语法](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [哔哩哔哩开放平台](https://open.bilibili.com/doc)
- [小红书开放平台快速接入](https://openaccount.xiaohongshu.com/docs/quick-start)

