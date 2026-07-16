# 安全政策

## 支持的版本

| 版本   | 是否受支持 |
| ------ | ---------- |
| v0.9.84+ | 是          |
| v0.9.83  | 仅关键安全修复 |
| < v0.9.83 | 否         |

## 报告漏洞

BookRank 使用 GitHub Private Vulnerability Reporting 接收安全漏洞报告。

- 请不要在公开 Issue 中披露漏洞细节。
- 请通过仓库的 **Security → Report a vulnerability** 提交私密报告。
- 如有紧急问题，也可发送邮件至 `gongyijie@gmail.com`，标题请注明 `[BookRank Security]`。

## 披露政策

- 收到报告后，维护者会在 7 个工作日内确认。
- 我们会评估影响范围，并在修复完成后发布安全公告。
- 在修复公开前，请避免公开漏洞细节，以保护所有用户。

## 安全配置建议

- 生产环境务必设置强随机 `SECRET_KEY` 与 `ADMIN_SECRET`。
- 使用外部 PostgreSQL 时，避免在日志中打印数据库连接字符串。
- 定期关注 Dependabot 安全更新并及时合并。
