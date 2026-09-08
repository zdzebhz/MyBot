# GitHub MVP

## 哪些功能不需要写代码

GitHub 自带邮件通知可以覆盖 PR、Issue、Review、评论、CI 结果、指派和 @提及等事件。它由两层设置共同决定：

1. 账号的通知设置中启用邮件，并选择已验证的收件邮箱。
2. 在目标仓库选择 Watch，或者只订阅 Issues、Pull requests、Actions 等自定义事件。

收到 GitHub 的 PR/Issue 通知邮件后，直接回复邮件也可以把内容作为评论发回对应会话。

## 哪些功能需要仓库文件

自动回复并不是普通通知设置。本仓库通过 `.github/workflows/pr-auto-reply.yml` 在外部用户创建、重新打开 PR，或将草稿转为 Ready for review 时自动留下确认评论。

当前规则：

- 仓库所有者自己创建的 PR 不回复。
- Bot 创建的 PR 不回复。
- 草稿 PR 暂不回复，转为 Ready for review 后回复。
- 每个 PR 只回复一次，重新运行工作流不会刷屏。
- 工作流不检出、不读取也不执行 PR 分支中的代码。
- 回复是固定模板，不调用 AI，也不需要任何额外密钥。

默认回复：

> 收到你的 PR，感谢贡献！我会尽快查看。

## 适用范围

GitHub Actions 工作流只作用于它所在的仓库。要让其他仓库也自动回复，需要把同类工作流加入相应仓库，或者以后升级为统一安装的 GitHub App。