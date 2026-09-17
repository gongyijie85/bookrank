# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual
label strings used in this repo's issue tracker, and documents the full label vocabulary so agents
apply consistent labels.

## Triage roles

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding
label string from this table.

## Full label vocabulary

Every new issue should carry at least one type label, one priority label (`p0`-`p3`) where the
priority is known, and the relevant module label(s).

### Type labels

| Label          | Meaning                                        |
| -------------- | ---------------------------------------------- |
| `bug`          | Something isn't working                        |
| `enhancement`  | New feature or request                         |
| `documentation`| Improvements or additions to documentation    |
| `question`     | Further information is requested               |
| `invalid`      | This doesn't seem right                        |
| `duplicate`    | This issue or pull request already exists      |
| `dependencies` | PRs that update a dependency file              |
| `javascript`   | PRs that update javascript code                |

### Priority labels

| Label | Meaning                       |
| ----- | ----------------------------- |
| `p0`  | 阻塞级缺陷，需立即处理        |
| `p1`  | 高优先级，近期迭代处理        |
| `p2`  | 中优先级，常规迭代处理        |
| `p3`  | 低优先级，可延后处理          |

### Module / area labels

| Label            | Meaning                                 |
| ---------------- | --------------------------------------- |
| `frontend`       | 桌面端前端（模板 / CSS / JS）           |
| `mobile`         | 移动端页面与样式                        |
| `backend`        | 后端逻辑与服务层                        |
| `i18n`           | 国际化与翻译（zh/en）                   |
| `api`            | API 端点与文档                          |
| `database`       | 数据模型 / 迁移 / 数据质量              |
| `crawler`        | 出版社爬虫与数据同步                    |
| `awards`         | 获奖书单模块                            |
| `new-books`      | 新书速递模块                            |
| `weekly-report`  | 周报系统                                |
| `deployment`     | 部署 / CI / 运维（Render、GitHub Actions） |
| `security`       | 安全相关（漏洞、CSRF、依赖）            |
| `performance`    | 性能优化                                |
| `testing`        | 测试与覆盖率                            |
| `refactor`       | 代码重构与质量改进                      |

### Operational labels (applied by automation, do not add manually)

| Label                | Meaning                               |
| -------------------- | ------------------------------------- |
| `data-drift`         | NYT category frequency drift detected |
| `operational-error`  | NYT frequency check operational error |
| `wayfinder:map`      | Wayfinder map issue                   |
| `wayfinder:prototype`| Wayfinder prototype ticket            |
| `wayfinder:research` | Wayfinder research ticket             |
| `wayfinder:grilling` | Wayfinder grilling ticket             |
| `wayfinder:task`     | Wayfinder task ticket                  |

Edit this file to match whatever vocabulary you actually use.
