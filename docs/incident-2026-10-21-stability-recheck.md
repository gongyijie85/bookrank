# BookRank3 稳定性、同步与流量复核交付（2026-10-21）

本轮直接检查、修复并测试当前 `D:\BookRank3` 工作区。开始时可正常访问，未遇到 Permission denied；保留已有未提交功能和用户修改，没有重置、切换分支、提交、推送或部署。本轮增量以前置补丁为基础，不能将工作区全部差分视为本轮新增内容。

用户提供的 Supabase 超额与限制通知仍为待恢复状态；本轮没有刷新控制台，也没有用健康检查推断额度已恢复。10 月 22 日额度补充的具体时刻与限制解除状态仍未知。目录中旧事故记录的用量数字属于过去的页面快照，不当作本轮实时测量。

## 根因与修复

| 路径 | 核查结果与本轮修复 |
| --- | --- |
| 超时、重试 | 既有 HTTP runner 已避免 `set -e` 在 curl 超时后直接退出，并限制写入请求只发送一次。本轮发现 HTTP 200 的空正文、HTML 或伪成功仍可假绿，且 running/failed 被误报 accepted；现核验 JSON 业务回执，区分 accepted、running、completed、failed、skipped、pending_verification。CI、Render/HF 监控也要求 `success is True` 且 `status == ready`。 |
| 重复提交 | 原有线程锁和冷却不能跨进程或重启识别同一次请求。本轮三类 cron 使用既有 `system_config` 主键原子受理、持久回执及比较更新；工作流用仓库、`GITHUB_RUN_ID` 和路径生成固定 `X-Idempotency-Key`，同一运行重跑不变。相同 key 重放读取原回执，不再次执行；提交确认不明也不自动重跑。无需新增表、依赖或迁移。 |
| 同步成功时间 | 同步摘要提交失败曾仍返回 synced；全部来源被跳过也曾推进成功时间。现分别标待核实、跳过，成功时间不推进。跳过是独立回执终态，不能当作数据刷新。 |
| 快照与来源状态 | 复核既有失败/空结果保留旧快照机制。本轮隔离爬虫 close 异常，避免清理失败抹掉来源报告；新增来源 fresh/stale/unknown、last_success_at、retained_previous。仅空成功时也持久化来源成功时间，后续失败不丢失证据，同时不推进全局发布或完整成功时间。 |
| 数据库缓存 | 既有详情、语言包、列表等缓存已减少热请求查库并合并冷请求。本轮发现部分详情、推荐、API、封面路径仍会读旧缓存或发布未提交数据，回滚后污染共享缓存。现未提交事务绕过共享缓存；封面解析使用 `persist=False`，避免顺便提交其他待保存数据。 |
| Google Books | 内容命中前仍进行配额读取或验证 API key，且 `{}` 负缓存被忽略。本轮改为内容缓存优先、显式识别空缓存；既有 429 冷却和有限重试保留。 |
| 图片 | 同步下载未与异步预取合并，且直接写目标文件可能暴露半张图片。本轮按 URL 共享一次在途下载，先写唯一临时文件，校验后原子替换；失败保留旧图、清理临时文件、关闭响应，随后可重试。另修复磁盘文件丢失时内存缓存并发删除引起的 KeyError。 |
| 压缩协商 | 既有修复已拒绝 gzip;q=0。本轮发现多行 Vary 被折叠丢失，304 缺少相同协商头；现合并全部 Vary 字段行并保留 304/206 的协商信息。符合 [RFC 9110 的 Vary 与 304 约定](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.4.5)。 |
| 初始化、健康 | 复核现有请求不迁移、迁移失败不删除版本记录、生产不自动播种。`/health` 只表示进程存活；`/health/ready` 只读核验数据库连接和生产迁移版本；业务来源、数量与新鲜度仍须单独验收。 |
| 发布 | 复核现有 NYT 404 按运行错误处理、Issue 正文限制并保留完整 artifact、静态导出空/失败不替换有效数据、候选仅上传 artifact。没有恢复直接推 main，也没有修改分支保护。 |

## 本轮修改文件

源代码和工作流：

- `app/__init__.py`、`app/setup.py`
- `app/routes/api/books.py`、`app/routes/api/cron.py`
- `app/services/cron_receipt.py`（新增）
- `app/services/api_utils.py`、`app/services/award_cover_cache.py`、`app/services/book_detail_cache.py`
- `app/services/recommendation_service.py`、`app/services/google_books_client.py`
- `scripts/workflow_http.py`、`update_books.py`
- `.github/workflows/ci.yml`、`.github/workflows/production-monitor.yml`

测试：

- 新增 `tests/test_cron_receipts.py`、`tests/test_image_cache_concurrency.py`
- 扩展 `tests/test_workflow_http.py`、`tests/test_update_books_snapshot.py`、`tests/test_response_compression.py`
- 扩展 `tests/test_detail_cache_invalidation.py`、`tests/test_book_details_api_cache.py`、`tests/test_award_cover_egress.py`
- 扩展 `tests/test_api_utils.py`、`tests/test_google_books_client.py`、`tests/test_local_postgres_runtime.py`

文档：`CHANGELOG.md` 追加三条本轮记录及本文件。最终精确清单和独立差分见 `.scratch/recheck-20261021/root/`。

## 实际验证

测试解释器使用仓库已有独立环境 `.scratch/incident-20261021/continuation-py313/venv/Scripts/python.exe`，实际 Python 3.13.0。使用已有 guard 强制 testing/SQLite 内存库、禁 dotenv、阻止非本机 socket/DNS、关闭邮件并清空外部 API key。没有读取 `.env`，没有连接生产库执行迁移或写入。

目标回归均有先失败再通过的证据，覆盖：

- 读请求超时重试；写请求响应丢失后不自动重投；同 key 重放读取 completed 回执，业务只执行一次。
- 受理、执行中、后台完成、部分失败、跳过、待核实；回执提交失败不执行；旧对象比较更新失败。
- 抓取失败/空结果/异常清理保留旧快照，来源成功时间跨连续失败保存，全部来源跳过不推进新鲜度。
- 真实 SQLite 的冷热缓存、flush 前后未提交变更、回滚污染与封面隐式提交。
- 同 URL 四并发、同步与异步共享下载、共享失败及后续重试、完整文件原子可见、失败保留旧图、内存失效竞争。
- gzip;q=0、通配符、长度、HEAD/Range/预压缩/no-transform、多行 Vary 和 304。
- 首个业务请求不迁移、迁移失败保留版本记录、数据库不可用与旧迁移版本导致未就绪。

| 检查 | 实际动作 | 结果 |
| --- | --- | --- |
| 全套 Python | `python -m pytest tests/`，保持覆盖率 70% 门禁 | **3460 passed，27 skipped，96 warnings，85.90% 覆盖率**，98.41 秒 |
| PostgreSQL | 新建专用 loopback PostgreSQL 18.4 集群，先核验 SHOW data_directory；`python -m pytest tests/test_external_postgres_init.py tests/test_local_postgres_runtime.py --no-cov -q` | **41 passed，4 warnings**，其中 **26 项真实 PostgreSQL**，覆盖迁移失败保留版本与旧数据、四并发持久 claim、重放及批导入；另含 15 项基础本地用例 |
| Ruff | `ruff check app/ tests/ run.py update_books.py scripts/workflow_http.py scripts/check_nyt_category_frequencies.py` | 通过 |
| 格式 | 同范围 `ruff format --check` | **280 文件**通过 |
| 类型 | `mypy app/`，无放宽参数 | **114 源文件，0 错误** |
| 前端 | `npm run lint:js`、`npm run test:frontend` | 零警告；**57 passed** |
| i18n | `python scripts/check_i18n_drift.py` | 通过；保留既有 en 两条、zh 一条缺译警告 |
| 工作流 | 两份修改后 YAML、23 个 run 脚本 Bash 语法、监控内嵌 Python 解析 | 通过；未在 GitHub Actions 实际运行 |
| 独立审查 | code-reviewer 与 python-reviewer 分别复核及运行目标回归 | 无遗留审查发现；发现的新鲜度和图片竞争均修复 |

本机没有 make，未声称执行过 `make check`；各相应门禁分别执行。本轮没有改翻译字符串或前端源文件，未重建或手改 `static/dist/`。

全套默认跳过 15 项显式 PostgreSQL 初始化测试、11 项显式 PostgreSQL 运行测试，以及 1 项 Windows 符号链接测试；并非将跳过项计为通过。两组 PostgreSQL 测试另行启用专用集群验证，结果见下方补充记录。全套的 96 条警告包括既有 PDF 字体接口弃用和测试 SQLite 资源告警，未据此扩大修改无关功能。

补充运行已完成：上述 26 个 PostgreSQL 跳过项均在显式本地集群上通过；符号链接项因本机无法建立测试所需链接，仍未运行，没有提权或修改权限。PostgreSQL 补充的四条警告为既有迁移接口弃用提示。日志为 `root/postgres-final.log`。

PostgreSQL 仅在新建 `.scratch/incident-20261021/continuation-pg/recheck-*/data` 下写测试数据，没有改系统服务；测试后已停止所属进程，核验原 PID 消失及 loopback 端口拒绝连接，保留数据目录。Windows 启动包装器曾等待整个子进程树；核实集群身份后仅终止本轮等待包装器，未重复启动数据库，测试另行执行并正常清理。版本为本机已安装 PG18.4，不能代替目标 PG17 的联合验证。

证据目录：`.scratch/recheck-20261021/`。`before/` 保存本轮编辑前文件；本轮差分仅用于相对已有补丁审查，不是完整独立发布包。各目标日志分布在 `root/`、`runtime_sync/`、`sync_pipeline/`、`cache_traffic/`。独立 Python 审查日志为 `python-review-final.log`。

## 未解决项与实际边界

1. Supabase 限额解除时间、恢复状态和真实同步结果未核实；Render/HF 的健康绿灯不构成这些证据。缓存减少后续流量，不能撤销本周期已发生的用量，也没有本轮生产流量下降比例。
2. 相同 key 的持久受理可以跨进程防重；不同 key、无 key 旧调用与独立 APScheduler 之间仍依赖原进程锁，没有跨任务全局租约、自动接管或过期后自动重跑。遗留 accepted/running/pending 回执须先查实际结果再受控恢复。
3. NYT 历史 404 的上游原因、Google 实际配额恢复和生产环境 key 注入尚未验证；没有擅自换端点或反复消耗配额。
4. 缓存与图片在途合并为进程级，跨 worker/实例不共享；保持现有单 worker 配置。缓存命中节省数据库返回流量，图片浏览器缓存与压缩节省相应应用传输，不能混称同一计费口径。
5. 快照为逐文件原子替换，进程内异常可恢复；不声称多文件在进程被强制终止时具有数据库事务式原子性。候选仍须检查汇总、分源文件与时间元数据一致后发布。

## Railway 与凭据

代码、部署配置和工作流未发现 Railway 项目关联；只有 Procfile 通用平台注释包含 Railway。该注释不足以确认实际使用。没有据预防性通知认定凭据已泄露，没有读取或输出密钥值，也没有撤销、替换、重授权或套用 Railway 数据库处理建议到 Supabase。

## 上线步骤（本轮未执行）

1. 先核实 Supabase 当时的配额及限制，确认业务只读查询可用，并检查现有同步回执、来源数量及成功时间；不要盲目重跑结果不明任务。
2. 从本轮精确差分与已有前置补丁中整理发布候选，保留用户功能。新文件 `cron_receipt.py` 和原有缓存模块等依赖必须完整纳入；不要只拷贝几个路由。经受保护分支 PR 和必需检查，不关闭保护、不直接推 main。
3. 在与目标相符的 Linux/Python3.13/PG17 隔离环境验证。检查已有迁移状态；本轮回执不需要新增迁移。若前置发布确需迁移，先备份并由操作者显式执行，失败保留版本历史，不由首个业务请求修库。
4. 经用户确认后发布候选。分别验收进程存活、数据库就绪和业务来源新鲜度；同 key 回放应只读回执。后台任务必须查看最终回执与实际数据，不能将 HTTP 200、accepted 或 running 当完成。
5. 对比发布前后的数据库请求/返回字节、图片回源数、响应大小、错误与超时，确认流量改善；静态数据只发布有效非空且元数据一致的候选。HuggingFace 继续通过 main 镜像链路发布，不单独改 Space 文件。

## 回滚方案

- 本地本轮回滚：按最终文件清单与 `before/` 逐文件恢复本轮前内容；新建文件在确认没有后续用户改动后再移除。不要对整个脏工作区执行 reset/clean，也不要批量覆盖用户文件。
- 应用上线回滚：重新部署上一批准版本及其原静态产物，保留已有数据、`system_config` 回执与迁移历史。没有本轮新迁移需要逆迁移，不删除 alembic_version 或回执来“解锁”。
- 数据回滚：静态候选异常时恢复上一有效快照整组文件及时间元数据；已提交的业务写入或结果不明任务先核对持久回执和数据，再决定恢复措施，不靠重跑同步代替回滚。
