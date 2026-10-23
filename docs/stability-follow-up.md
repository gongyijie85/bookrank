# BookRank 稳定性后续安排

本轮已开始执行本地发布准备。保留既有工作区和用户功能；推送、PR、合并、部署、生产同步写入及权限或凭据变更仍按原约定单独确认。没有设定后台自动重跑或生产发布日程。

## 当前判定

- 2026-10-23 续办已完成当前 main 的隔离整合和联合验证：Linux/Python 3.13/PostgreSQL 17 全套 **4025 通过、零跳过、87.15%**，真实 Gunicorn 11 项检查通过；Windows **3998 通过、27 跳过、86.86%**，前端 **383 通过**。代码与 Python 独立审查均无未解决发现。详见 [本轮交付报告](stability-integration-2026-10-23.md)。这仍是本地候选，生产恢复和数据同步尚未验收。
- 上轮完整工作区测试通过，但“工作区通过”不等于“独立发布候选通过”。上轮 27 文件差分依赖已有补丁，且 Windows 写文件产生 CRCRLF 换行，不能直接作为发布包。
- 已只读核对 GitHub：当前 `main` 为 `a86acdbff3a7c61f351bda9e29795dfcf34d529f`；本地 HEAD 为 `7fc28bb87006a2c1f5feffae3affeabfe2b3658d`，二者分叉，共同基点为 `da6bab83212fba7f3b547238114869585acb5743`。真正 PR 前必须基于当时最新 main 隔离整合，避免覆盖已合并的页面和功能。
- 本地 `static/data/all_books.json` 七个来源均为空，`update_time.json` 为历史时间且 `total_books=0`，没有 `sync_attempt.json`。这些文件不构成有效的数据发布候选。代码候选补丁不包含任何 `static/data/` 更新。
- Supabase 额度与限制恢复仍未知；不能按补充额度日期推定恢复，也不能用 Render/HF 健康绿灯代替业务验收。
- 前次补修后原工作区完整验证为 **3490 通过、27 跳过、覆盖率 85.95%**；该历史结果不替代本轮独立候选结果，也不改变下面旧候选失败的记录。

## 执行顺序与完成标准

| 顺序 | 工作 | 负责人 | 完成标准与当前状态 |
| --- | --- | --- | --- |
| 1 | 补纯读取的任务回执查询 | Codex，本地 | 已完成。新增 30 项回归，目标 156 项通过；两位独立审查各自运行回执测试 48 项通过。真实限流 429 的 no-store 遗漏已修复。 |
| 2 | 补丁重新生成、依赖闭包与独立候选 | Codex，本地 | 已完成依赖审计和候选试验：84 个必要/前置路径、9 个相关回归文件及本计划。LF 补丁在声明基线成功应用，全树逐字节匹配；但候选全套 **3166 通过、23 失败、27 跳过**，尚未形成可发布候选。失败表明缓存接线、首页/移动页和周报展示前置仍不完整，不能删测试冒充通过。 |
| 3 | 在最新 main 隔离整合 | Codex，本地 | 已完成。基于本轮核对的 main `a86acdb` 三方整合，保留其页面、安全返回、异步封面及后台数据库连接释放行为；原工作区核对的 105 个文件哈希未变。差分可在该 main 基线干净应用，另有逐文件清单。尚未提交、推送或创建 PR。 |
| 4 | 目标环境联合验证 | Codex，隔离环境 | 已完成 Linux/Python 3.13.17/Gunicorn 23.0.0/PostgreSQL 17.11 联合验证，4025 项零跳过，含 26 项真实 PG 用例及 Linux 符号链接检查。Gunicorn 验证只读请求、零播种、压缩和 worker 替换；测试进程、PG 与本轮符号链接均已清理。 |
| 5 | 额度、数据与发布前核验 | 平台登录由用户控制，Codex 只读核查 | 待确认恢复状态。记录 Supabase 当前限制、来源真实数量、最后成功时间、未决回执和发布前流量；结果不明的任务不盲目重提。 |
| 6 | 受保护 PR 与发布 | 用户确认后由 Codex 执行 | 前述门禁通过、候选与回滚版本明确后，再确认推送/PR及部署范围。保留分支保护和必需检查；HF 继续由 main 镜像链路发布。 |
| 7 | 发布后业务与流量验收 | Codex，只读 | 核对实际部署 SHA、来源数量/新鲜度、最终回执、错误率和同口径流量。未取得这些证据前，状态保持“上线待验收”。 |

## 安全的回执查询

本地新增 `GET /api/cron/receipt`：沿用 `CRON_SECRET` 的 Bearer 鉴权，`X-Idempotency-Key` 使用原提交的相同标识。该入口只查询既有行，禁止创建回执、提交事务或启动任务。

| 返回 | 含义 |
| --- | --- |
| 200 | 返回既有回执；accepted/running/pending_verification/skipped 都不能认定来源已刷新 |
| 400 | 标识缺失或格式非法，没有执行查询或任务 |
| 401 | 未授权，没有查询回执 |
| 404 | 没有找到既有回执，没有创建新任务；不能据此自动重提 |
| 429 | 限流；没有进入业务处理，响应也不能缓存 |
| 503 | 数据库或回执不可核验；不返回损坏原文和内部 token |

不要把三个 `/api/cron/trigger-*` 或 `/api/cron/sync-award-covers` 触发接口当查询接口：即使既有标识会重放，未知标识仍会受理新任务。批导入状态同样应读取已有回执，不调用导入接口“探测”。

## 上线后验收记录

每项记录实际观察时间、批准候选 SHA、部署 SHA、证据位置和 PASS/FAIL/PENDING；未观察到的字段留待核实，不用示例数据填充。

| 验收项 | 数据来源 | 通过条件 |
| --- | --- | --- |
| 进程存活 | `GET /health` | 只确认进程，不代替数据库或业务验收 |
| 数据库就绪 | `GET /health/ready` | JSON 严格为 `success=true,status=ready`，迁移版本匹配；HTML/空 HTTP200 不通过 |
| cron 最终结果 | 新只读回执入口 | 原任务标识匹配；最终状态与真实业务记录一致，不能仅看受理或运行中 |
| 自动新书同步 | `GET /api/admin/new-books/last-sync` | `last_auto_sync_time` 与 `result.status/pending_publishers/publishers[]` 一致；失败、跳过和未决不推进成功时间 |
| 来源健康 | `GET /api/admin/new-books/source-health` | 来源开关、连续失败、last_attempt_at、last_success_batch_id 与实际抓取结果相符；尝试时间不能当成功时间 |
| 静态数据 | 汇总、分源文件及 `sync_attempt.json`、`update_time.json` | 非空有效数据、总数一致、失败源保留旧数据与成功时间；检查各源 last_success_at 的实际年龄 |
| 流量效果 | Supabase 和 Render 各自统计 | 在相近请求量和同一业务路径下比较数据库返回字节、图片回源、响应大小及错误率；没有对照证据就不写降幅 |

手工同步的 `/api/new-books/sync/status` 仅为进程内状态；重启后 idle 不能证明旧 cron 成功。静态报告 `freshness=fresh` 仅表示当轮抓取成功，仍需结合时间判断是否陈旧。

## 回滚及停止条件

- 任一候选缺依赖、应用检查失败、回归失败或未在最新 main 完成整合，停止推进发布，保留证据和原工作区。
- 发现空数据、来源结果未知、迁移不匹配或 Supabase 仍受限，保留旧有效数据，不发起重复同步来试探。
- 应用回滚使用上一批准版本及原静态产物；保留数据库、迁移历史和任务回执，不删除版本号或回执“解锁”。
- 本地只读查询的独立差分和编辑前备份保存在 `.scratch/stability-release-prep/receipt-query/`；按文件复核后恢复，不能 reset/clean 整个脏工作区。

## 本轮证据

- `.scratch/stability-release-prep/dependency-audit.json`：依赖闭包、旧包问题、main 分叉与范围限制。
- `.scratch/stability-release-prep/receipt-query/`：新增接口的编辑前备份、失败与通过日志。
- `.scratch/stability-release-prep/candidate-manifest.json`：本地审查候选文件和哈希；基于本地 HEAD，不能直接发布到当前 main。
- `.scratch/stability-release-prep/workspace-pytest.log` 与 `candidate-pytest.log`：原工作区通过、独立候选失败的两份完整日志。
- `.scratch/stability-release-prep/` 下的应用检查、测试和最终状态记录，以实际结果为准；旧包和上轮测试日志保持原样，不重新标记为本轮成功。
