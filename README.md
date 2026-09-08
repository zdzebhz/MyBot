# MyBot

一个面向个人使用的信息助理项目，当前处于方案选型阶段，尚未开始功能开发。

## 目标

1. 接收 GitHub 上与自己相关的 Pull Request、Issue、Review、CI 等事件并发送邮件提醒。
2. 在别人提交 PR 时，按规则自动留下确认或审查回复。
3. 每日收集 B 站、小红书等平台上最新的 AI 资讯，去重、摘要后推送。

## 当前状态

- [x] 建立项目仓库
- [x] 记录需求与候选架构
- [ ] 确定最终方案
- [ ] 明确邮件服务、部署位置和信息源范围
- [ ] 开始实现

详细比较见 [docs/ARCHITECTURE_OPTIONS.md](docs/ARCHITECTURE_OPTIONS.md)。

## 安全边界

- 不把 GitHub Token、邮箱授权码、Cookie 等密钥提交到仓库。
- GitHub 能力优先使用最小权限的 GitHub App。
- 社交平台优先采用官方 API、RSS、公开网页或经授权的访问方式。
- 自动回复先从固定模板和白名单仓库开始，避免模型误操作。

