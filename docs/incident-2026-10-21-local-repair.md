# BookRank 故障本地修复记录（2026-10-21）

后续已补充 Python 3.13、真实本地 PostgreSQL、Linux/Gunicorn 和 Qoder/Grok 审查。最新数据播种、初始化入口、发布依赖与平台核查见文末“第三阶段继续检查”和“最终整合验收”；前文保留各阶段当时的版本与结果。全部结果仍为本地验收，未发布。

## 范围与当前状态

- 工作区 `D:\BookRank3` 可读写，Git 可访问；未再出现 E 盘或 Permission denied。
- 分支：`chore-placeholder-source-and-gb-backoff`。
- 开始时 HEAD：`7fc28bb87006a2c1f5feffae3affeabfe2b3658d`。
- 开始时已有大量已修改和未跟踪文件。本次在原补丁上精准修改，未重置、清空、切换分支或提交。
- 本次未 push、创建 PR、合并、部署、请求生产业务、重跑生产同步、修改生产数据/权限、升级方案或创建凭据。
- 操作前副本、原状态、本次独立差分及测试日志在 `D:\BookRank3\.scratch\incident-20261021\`；它们是本地审查材料，不是发布包。

## 已确认根因与修复

### 安全重试与告警

原工作流在 `set -e` 下用命令替换获取 curl 结果。curl 首次退出 28 时，shell 先退出，后续重试/分类代码无法执行。新书、封面、周报 cron 虽使用 GET，实质会写入，不能按普通只读 GET 重试。

新增标准库 HTTP runner 调用 curl，分别记录 transport、HTTP、业务确认和重试次数。只读请求最多三次、指数退避、受总预算限制。无持久幂等保障的提交只发一次；超时、网关错误或确认不完整时为 `pending_verification`。收到异步触发确认仅为 `accepted`，不能当作完成。

批导入已有事务内 `BatchImportReceipt`：重试固定请求原始字节和 batch_id，匹配持久回执才确认成功。隔离 SQLite 测试模拟首次已 commit 后响应丢失，重放后数据及回执各一条。

observe 不再因前一阶段提交结果不明而被自动跳过。告警单独报告未配置、无需发送、发送失败与送达；只有明确成功回执才认可送达。HTML、非法 JSON、空对象、空 204 和布尔假零均不算成功。来源告警 API 保留 success 契约，增加 delivery；空 GitHub 客户端、零 issue 编号和 noop 不再冒充通知。

监控通知步骤移除 `continue-on-error`，避免失败步骤的 conclusion 被改为 success 后错误抑制下一次通知；原始探测失败仍保留。issue 正文限制为 12KB，完整报告保留 artifact。数据更新只上传候选 artifact，移除直接推 main，后续仍须受保护分支和必需检查。

### 数据与来源保护

原 `update_books.py` 将抓取异常、不可用爬虫转成 `[]`，无条件覆盖快照和更新时间，且未按爬虫声明注入 API key。

现在区分失败、无效结果、成功空结果及有效非空结果。失败/空结果不清空旧有效数据；部分成功只替换有效来源，保留失败来源。全失败只更新尝试报告。先序列化并暂存，再逐文件原子替换；进程内替换异常尝试恢复本轮已替换文件。

时间口径：

- `sync_attempt.json.attempted_at`：最近尝试。
- `update_time.json.published_at`：本轮有效来源的发布时间。
- `source_success_at`：各来源确认成功时间。
- 兼容字段 `timestamp`：部分成功保留旧值，完整成功才更新。
- `last_complete_success_at`：完整成功时间；没有证据的历史时间保持未知，不用 Git 提交时间推定。

API key 只核查变量名映射与配置状态，补齐 GOOGLE_API_KEY/PRH_API_KEY 注入，不打印内容。底层请求日志统一移除用户名、密码、query 和 fragment，异常仅记录类型；三类含随机假凭据的模拟异常回归验证日志不泄露凭据。Google 抓取取消双层重试，增加同进程 429 冷却和有限 GET 时间预算。爬虫分页失败通过 CrawlOutcome.errors 传到实际同步引擎；已入库有效记录保留，但出版社/全局成功时间和成功计数不推进。

NYT 元数据读取增加有限重试，404 归为运行错误而非分类漂移。官方规格仍列出 lists/names.json，未擅自换端点，历史 404 的实际原因仍待核实。

### 缓存与传输

保留工作区已有语言包、详情、失效缓存补丁。分类冷请求复用已有 DetailCache 合并同键加载；事务内未提交内容绕过共享加载与快照发布。测试通过实际 SQL 监听确认榜单热命中不增加译文查询，四个并发冷请求只回源一次。

修复 ttl=0 被默认值吞掉、文件缓存晋升内存导致寿命延长，以及并发文件写共用临时文件。使用剩余 TTL 与唯一临时文件原子替换。

gzip 使用编码质量值，拒绝 gzip;q=0，保留原 Vary 并追加 Accept-Encoding，按传输字节更新 Content-Length。跳过 HEAD、206/Range、流式、已压缩和 no-transform 响应，处理 ETag。图片有效缓存对齐七天；临时占位/图片错误/静态 404 使用 no-store，指纹静态文件才使用 immutable。

数据库查询缓存主要减少 Supabase 数据库返回流量；浏览器缓存、gzip 和响应字段裁剪才直接减少相应 Render 对外响应流量。它们不能撤销本周期已产生的超额用量。本次没有重复新增分页层，保留既有列表字段裁剪及分页补丁并运行回归。

### 启动与就绪

确认原首次业务请求会迁移；失败后可能 DELETE alembic_version、自动 stamp/create_all，且失败仍可能被标为初始化成功。

现在请求路径不执行迁移。生产也不在延迟后台初始化时自动清洗或播种。迁移失败保留版本历史；本地由已有应用工厂创建模型表，首次业务请求只初始化基础数据，失败不标成功。真实新建 SQLite 应用回归已覆盖。

Gunicorn 关闭 preload，避免调度器和连接池在 master 中初始化后 fork；Procfile 同步移除 preload。APScheduler 后台执行并发限制为一，生产 MAX_WORKERS 尊重环境配置并保持上限。cron 启动前原子预留锁，防止线程开始前的重复提交，线程启动失败释放锁。

- `/health`：进程存活，不查库。
- `/health/ready`：连接及生产迁移版本只读核对，不迁移、不抓取、不扫描业务数据。
- 榜单、来源、封面、翻译数据完整性：另行业务验收，健康检查绿灯不能代替。

生产连接池已有 2+1 连接、15 秒池等待、5 秒连接超时、15 秒语句超时；未无证据扩大连接数或延长超时。这些界限及后台并发调整仍需生产指标验证，不能据此断言 Render 10000 端口超时已解决。

## 本次修改文件清单

以下只列本次触及文件；同一文件可能同时包含用户原补丁。

- 工作流：`.github/workflows/{trigger-new-books-sync,trigger-award-cover-sync,trigger-weekly-report,site-crawl-pipeline,update-books,production-monitor,ci,recover-hf-space}.yml`。
- HTTP/NYT 脚本：`scripts/workflow_http.py`（新增）、`scripts/check_nyt_category_frequencies.py`。
- 快照：`update_books.py`。
- 爬虫/API：`app/services/api_utils.py`、`google_books_client.py`、`publisher_crawler/{base_crawler,google_books,google_books_publisher,macmillan,open_library,prh_api}.py`、`new_book/sync_engine.py`。
- 缓存/响应：`app/services/{book_service,cache_service}.py`、`app/__init__.py`（响应头函数）、`app/routes/main.py`（图片路由）。
- 启动/健康/告警：`run.py`、`gunicorn.conf.py`、`Procfile`、`app/config.py`、`app/setup.py`、`app/services/health_service.py`、`app/routes/{health,admin}.py`。
- 新测试：`tests/{test_workflow_http,test_workflow_source_alert,test_update_books_snapshot,test_publisher_crawler_failures,test_response_compression,test_book_category_singleflight,test_cache_expiry_safety,test_runtime_safety}.py`。
- 扩展测试：`tests/{test_google_books_client,test_nyt_frequency_check,test_sync_engine,test_app_init}.py`。
- 文档：`README.md`、`CHANGELOG.md`、本记录。

## 验证与证据

测试解释器是项目现有 `.venv` Python 3.11.9；仓库/CI 目标为 Python 3.13，本机这次没有在 3.13 上运行测试。未新增生产依赖。前端工具原未安装，按现有 package-lock 执行 npm ci --ignore-scripts，未修改锁文件。

测试隔离：通过 `PYTHONPATH=D:\BookRank3\.scratch\incident-20261021\guard` 加载仅用于本次验证的 sitecustomize，禁用 dotenv，指定 testing/SQLite 内存库、禁用邮件并清空外部 API key，阻止非本机 socket/DNS。mock 服务仍可正常替换；没有借测试连接生产数据库。该隔离文件不属于应用代码。

| 检查 | 实际命令或等价动作 | 结果 |
| --- | --- | --- |
| 首轮全套 | `.venv\Scripts\python.exe -m pytest tests/` | 3271 passed，1 skipped，覆盖率 84.69%，136.37 秒 |
| 审查补修后的第二轮 | 同上 | 3297 passed、7 failed、1 skipped；新增告警测试未显式设置鉴权配置，受旧测试残留配置影响，随后补齐本测试的配置与恢复，不修改鉴权实现或断言 |
| 最终全套 | 同上，含全部审查补修 | **3307 passed，1 skipped，覆盖率 85.61%，129.24 秒**；日志 full-pytest-verified.log |
| Lint | `.venv\Scripts\ruff.exe check app/ tests/ run.py update_books.py scripts/workflow_http.py scripts/check_nyt_category_frequencies.py` | 通过 |
| 格式 | 同范围 `ruff format --check` | 通过，272 文件 |
| 类型 | `.venv\Scripts\mypy.exe app/`，无额外放宽参数 | 113 源文件，0 错误 |
| JS lint | `npm run lint:js` | 通过，零警告门禁 |
| 前端测试 | `npm run test:frontend` | 57 passed |
| i18n drift | `.venv\Scripts\python.exe scripts/check_i18n_drift.py` | 通过；现有 en 两条/zh 一条缺译警告保留 |
| 翻译聚合目标 | pybabel extract → update → compile，在现有目录的隔离副本执行 | 三步均退出 0，保留用户已有目录补丁 |
| 工作流结构 | 9 份 YAML 解析，54 个 run 脚本 Git Bash 语法检查 | 通过；没有在 GitHub Actions 实际运行 |
| 差分空白检查 | `git diff --check` | 通过；Git 提示既有 LF/CRLF 转换不影响此结论 |

首次 lint:js 因 eslint 未安装未能运行，安装已有锁文件依赖后通过。早期 mypy 两个新增 nullable mimetype 错误已修。独立审查稳定复现测试顺序的五项失败：test_app_init 的 session 客户端残留 lang=zh，触发周报日期 Mock 格式化；只给该 Cookie 测试加 finally 恢复原状态，不改周报逻辑或断言，原失败顺序现 161 项通过。

Windows 当前没有 make，因此未声称 `make check`/`make i18n-drift` 原命令运行成功；已逐项执行其 lint/type/test/翻译动作，并单独运行格式、前端和 drift 门禁。翻译动作使用隔离副本，未覆盖用户已有目录。

唯一跳过项为 `test_symlinked_fixture_files_are_rejected_including_chains`：当前 Windows 无法创建测试所需 symlink，沿用测试自身的 skip；没有提权、改 ACL 或注册表。第二轮新增告警测试的配置隔离补修后，按旧源健康→旧源告警→新告警→爬虫安全顺序 33 项通过。两位独立审查代理发现的通知、同步状态传播、本地初始化和日志泄露问题均已修复复核；最终审查没有剩余 P1/P2 发现，仅代表本地审查。

安装既有前端锁文件工具时，npm audit 报一项开发工具传递依赖 `brace-expansion <=1.1.20` high；未自动更新依赖或更改锁文件，后续应单独核查开发工具修复。

新增回归覆盖首次超时、耗尽、已执行但响应丢失、同 batch 重复、告警失败/缺配置/无效回执、全部及部分来源失败、保留快照、准确时间、原子替换失败、分页中途失败、热缓存 SQL 次数、四线程冷缓存、事务未提交隔离、TTL、gzip;q=0、Vary 及临时图片策略。先红后绿日志及独立审查材料在 evidence 目录。

## 平台只读核查

重新读取平台邮件并调用 Supabase 只读项目/组织接口：

- 10 月 18 日 Supabase 邮件明确为 13.03 GB / 5.5 GB，期限已缩短到 **2026-10-21**；没有具体时分或时区，不能推定为当日结束。只读接口返回 Free；名为 bookrank-db 的项目 ACTIVE_HEALTHY。这不能证明额度限制解除，也没有提供当前额度/限制状态。需当天核对组织 Usage/Billing/Fair Use 状态，必要时联系平台支持确认实际期限与限制。未自动升级或关闭 spend cap，未假定等重置即可安全。
- Render 10 月 18 日邮件称 5GB 已用完、后续自动计费；10 月 20 日邮件再次报告实例端口 10000 TCP 超时。未获得实际运行日志、CPU/内存/连接池/worker 指标，不能判定为 Supabase 限额导致。两个平台的问题相互独立。
- 10 月 30 日 Data API 通知只影响以后创建的新 public 表；已有表维持原 grants。代码检索未发现主应用使用 supabase-js/PostgREST/GraphQL，当前服务数据层为 SQLAlchemy PostgreSQL 连接。因此本次无需开放表权限；若之后有实际 Data API 调用，只对具体表、具体角色授予所需操作，并单独验证 RLS，禁止对内部表批量授权。

参考：[Supabase 额度限制](https://supabase.com/docs/guides/platform/billing-faq)、[Render 流量计费](https://render.com/docs/outbound-bandwidth)、[10 月 30 日变更及直接连接不受影响说明](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically)。

## 未解决风险、后续顺序与回滚

1. **先处理平台时限。** 人工核对当天实际额度、限制和超额账单，确认是否需要支持介入或付费变更。涉及升级、配额或权限操作须另行批准；本次不执行。
2. **整理发布差分并运行目标环境检查。** 当前分支混有大量用户补丁，不能将整个 dirty 工作区直接发布。先挑选本次修改、在 Python 3.13/Linux CI 跑相同检查，保留必需检查和分支保护。创建 PR、push、合并和部署须另行批准。
3. **隔离 PostgreSQL/预发布验证。** 本次 SQLite 证明应用级行为，不能替代真实 PostgreSQL、Gunicorn fork、Render 网关及配额限制实验。迁移前备份并审查待执行迁移；显式迁移、schema heads、基础数据分别验收，禁止通过业务请求迁移或自动 stamp。
4. **先发布保护，再受控验证。** 查看任务是否已运行及实际回执，未知结果先核实，避免手动重跑写入。发布后分开验收存活、就绪、真实业务、后台完成及告警回执，连续观察 worker 重启、延迟、连接池等待、429、字节数；单次健康绿灯不算根因关闭。
5. **数据恢复需独立批准。** 当前本地静态 update_time.json 表示零数据；没有将历史候选 531c77f258e9b017d01af7a871b1b53c542e229d 直接恢复。该候选只有两源非空，完整性、抓取成功时间和新鲜度不足。应核对每源记录及成功证据，生成候选数据，经受保护流程发布。
6. **回滚只回应用/候选数据。** 部署前记录已验证的应用提交、环境配置和数据快照；应用回退保持安全重试与只读初始化保护。不要恢复失败后删版本记录、盲重投或空快照覆盖的旧行为。数据库采用向前修复，涉及回滚迁移或数据恢复必须先备份、演练和批准。

保留的能力边界：cron 仍无跨进程持久请求 ID/关联完成查询，靠单次提交避免危险重试；内存缓存/锁及 429 冷却仅在进程内；快照逐文件原子和进程异常恢复不保证机器断电时跨文件事务；后续候选发布应成批校验。尚未证实历史 NYT 404 根因、生产 key 配置存在性、当前真实 quota/限制、Render TCP 超时根因、跨进程表现或实际流量节省比例。

## 继续验证：Python 3.13、真实 PostgreSQL 与外部审查

用户授权继续本地修复，并允许调用 Grok、Qoder。分支与 HEAD 未变，继续保留原有补丁；没有 push、PR、合并、部署或生产写入。

### 新确认并修复的问题

1. **真实 PostgreSQL 并发回执冲突。** 两个 HTTP 线程经 Barrier 同时读到回执不存在，同一 batch 原来返回 `[200, 500]`。根因为 `batch_import_receipts_pkey` 唯一约束竞争。现在只识别 SQLSTATE 23505 且约束名精确匹配的情况，回滚后重新读取已提交回执，并核对 batch、source 和 digest；匹配才返回 duplicate，不同内容返回 409，其他唯一冲突仍失败。异常不会把 SQL 参数写入通用 API 日志。并发、内容冲突及其他约束错误回归先红后绿。
2. **后台失败计数丢失。** Qoder 确认 `_scheduler_wrapper` 在退出 Flask 应用上下文后记录失败，数据库操作实际失败，只有内存计数增加。现在在上下文内处理错误，先回滚任务残留事务再记录失败；即使 rollback 自身失败，也继续报告原任务异常类型。真实 SQLite 回归确认失败计数持久化且任务未提交结果没有被顺带提交。
3. **后台 webhook 误报送达与隐式重复 POST。** 原来只调用 post 就记“已发送”。任务、资源与爬虫漂移告警现在统一核对 HTTP 2xx 与明确 JSON 成功回执；HTML/空回执/业务拒绝/异常不算送达，缺配置明确未发送。单次发送不自动跟随重定向；真实 loopback HTTPServer 307 回归确认只有一个 POST。错误日志仅保留异常类型。

本阶段新增/修改产品文件为 `app/services/batch_import_service.py`、`app/setup.py`；新增 `tests/test_local_postgres_runtime.py`、`tests/test_scheduler_failure_reporting.py`；更新本报告和 CHANGELOG。前一阶段快照、缓存与工作流补丁继续保留。

### 工具与环境边界

- **Python 3.13.0 / Windows：** 在 `.scratch/incident-20261021/continuation-py313/venv` 创建独立环境，按原 requirements 安装，未修改既有 `.venv`、全局环境或依赖清单。首轮 3307 passed、1 skipped、85.60%；后续整合开启真实 PostgreSQL 用例。
- **真实 PostgreSQL 18.4：** 新建专用 data 目录，仅监听 127.0.0.1，未改系统服务、权限或生产配置。测试先核对 manifest 所属目录、loopback 和 `SHOW data_directory`，再创建唯一测试 schema。验证只读 readiness、缺/旧/当前版本、生产业务不迁移、连接归还及断开后恢复、已提交但响应丢失重放、回执失败整体回滚、并发重复与冲突。Supabase 当前元数据为 PostgreSQL 17.6.1.127，因此本地 PG18 通过不能代替目标 PG17 验证。
- **Linux / WSL / Python 3.12.3 / Gunicorn 23：** Docker 引擎未运行，没有启动服务。使用 WSL 独立临时环境，实际启动 Gunicorn，验证调度器只在 worker 创建、单后台线程、存活/就绪/业务路径不迁移、请求仅 SELECT、worker 替换后恢复。Gunicorn 已正常退出。该 harness 使用 SQLite 与生产路径标志，不能称为真实生产配置加 PostgreSQL 的联合运行验收。
- **Qoder：** 通过 Orca 原生终端只读任务取得实际代码审查结果和恰好一次 succeeded 完成回执，任务资源已释放；其 P2 发现已修复。终端界面模型名为 Qwen3.8-Flash，不独立断言底层 provider 身份。启动时工具自行显示更新提示，操作者没有执行升级命令，更新是否完成未核实。
- **Grok：** 通过 Orca 原生 structured worker 实际读取代码和分析，但单次八分钟上限内未取得最终结论/完成回执；停止并释放，不重投，也不算审查通过。不能以启动、心跳或读取成功替代审查完成。
- **独立代码审查：** PostgreSQL 恢复逻辑及后台上下文、回滚异常、307 重投已复核，没有剩余 P1/P2 发现；仅为本地代码审查。

### 本阶段实际验证

测试仍使用 dotenv 禁用、外部 API key 清空及非本机网络阻断策略。PG 用例是显式 opt-in：默认没有 manifest 时只跳过，不接 PostgreSQL；本轮整合明确开启专用本机实例。

```powershell
$env:PYTHONPATH='D:\BookRank3\.scratch\incident-20261021\guard'
$env:BOOKRANK_LOCAL_PG_MANIFEST='D:\BookRank3\.scratch\incident-20261021\continuation-pg\active-local-run.json'
$env:COVERAGE_FILE='D:\BookRank3\.scratch\incident-20261021\continuation-py313\.coverage-completed'
.\.scratch\incident-20261021\continuation-py313\venv\Scripts\python.exe -m pytest tests/
```

| 检查 | 结果 / 证据 |
| --- | --- |
| Python3.13 + 真实 PG 首轮整合 | 3328 passed、1 skipped、85.30%，127.86 秒；发生在最后两个边界回归前，日志 pytest-integrated-final.log |
| 最终整合全套 | **3330 passed、1 skipped、85.79%，126.82 秒**；Python 3.13，包含真实 PG 9 项与全部14项后台回归；日志 pytest-completed.log |
| 后台/告警/setup/漂移定向 | 83 passed；scheduler-final.log；新增14项覆盖上下文、未提交数据、回执、rollback 再失败、真实307 |
| PG/批导入/workflow 定向 | 72 passed；默认不启用 manifest 时 PG 9 项明确 skip |
| Ruff / 格式 / mypy | Python3.13 环境通过，275 文件格式、113 源文件零类型错误 |
| Linux/Gunicorn | 8 项检查通过，见 continuation-linux/result.json；未联合真实 PG |

本轮专用 PostgreSQL 已按精确 data_directory 停止：stop 退出0，原进程退出，loopback 端口拒绝新连接，数据与日志保留，manifest.started=false。上述整合命令是在实例运行时执行；重新验证需先按 continuation-pg/VALIDATION.md 建立并确认专用实例，不能将 manifest 改指现有或生产数据库。Linux Gunicorn 及两个外部审查 worker 也已退出/释放。

Python 3.13 保留 ResourceWarning（SQLite 连接未关闭）和 PDF 字体等弃用警告，没有屏蔽；这不能直接证明生产 PostgreSQL 泄漏。唯一 Windows symlink 跳过项仍需目标 Linux CI 验证。本次没有更改 production dependencies 或锁文件。

证据目录：`continuation-py313/`、`continuation-pg/`、`continuation-linux/`、`continuation-fixes/`、`continuation-external/`（均位于本次 .scratch 目录）。外部结果与生命周期见 `continuation-external/external-review-summary.md`、`review-results.json`。

继续阶段只读平台刷新仍显示 bookrank-db ACTIVE_HEALTHY；针对更新通知的邮件检索没有得到解除限制证据。配额是否限制、10月21日具体截止时刻、Render TCP 超时根因、历史 NYT 404、数据恢复和实际流量收益仍未核实。发布、生产迁移、付费或权限变更仍须另行批准。

## 第三阶段继续检查：数据播种、初始化入口与发布依赖

### 新确认的数据保护问题

静态播种原先即使读取空列表也把 Publisher.last_sync_at 写成当前时间；部分导入失败仍返回 success=True。现在静态导入明确标为 static_snapshot，不推进真实抓取的 last_sync_at/sync_count；空、失败、部分失败分别报告，已经成功提交的有效记录保留。SyncRequestGate 只对成功或已有可展示数据完成一次性兜底；失败/空结果/异常冷却60秒后可再尝试。它仍是首次展示兜底，不负责调度补齐失败来源。

导出校验原先用 str() 接受数字、布尔、列表书名/作者，后续读取会因 .strip() 出错。现在 title/author 必须为非空文本，非法抓取结果保留原快照。静态 reader 同样提前隔离不合规身份及可选字段，避免坏行到数据库提交时拖垮同源有效行。本轮未更改 static/data 中任何 JSON 文件。

历史候选 531c77f258e9b017d01af7a871b1b53c542e229d 经本地逐记录审计仍只有 HarperCollins/Hachette 各100条、其余五源为空。Harper100条均缺出版日期/简介，93条缺封面；Hachette94条有日期，最晚为2026-08-11。候选没有可信逐条抓取成功时间，当前30日窗口无可确认新书。ISBN校验、域名与内部重复检查不能证明在线真实性、新鲜度或完整性；未恢复该候选。完整证据见 `.scratch/incident-20261021/snapshot-candidate-audit/AUDIT.md` 和 candidate-manifest.json。

### 平台只读事实刷新

- Render 控制台显示当前成功部署提交为 a86acdbff3a7c61f351bda9e29795dfcf34d529f，仍是 Free；本月该服务 Outbound Bandwidth 为 **13.79 GB**。这是服务用量显示，未据此计算最终账单或假定全部是超额收费流量。CPU/内存历史需付费实例才能查看，本次未升级。
- Events 确认10月19日、20日多次端口10000 i/o timeout 后恢复；事件显示时区未单独确认。生产日志在10月21日05:16:47、06:17:09、08:04:36 UTC 出现“首次请求，初始化数据库”，随后启动 Alembic。证明部署仍包含原首次请求路径，本地修复尚未上线；这些记录不能单独证明迁移耗时、内存耗尽、连接池堵塞或额度限制导致超时。
- Supabase 日志窗口固定为2026-10-20 09:00至10-21 09:00 UTC：PostgREST14.5/authenticator 产生2694条 ERROR/3F000，另有一条 supabase_admin 的 LOG/08006。3F000 是 invalid_schema_name，不能当成额度 HTTP402；具体缺失schema、请求来源与Flask超时的因果关系仍未知。只读统计未读取SQL正文或凭据，未执行生产修复。[PostgreSQL错误码文档](https://www.postgresql.org/docs/17/errcodes-appendix.html)
- Supabase Usage 页面跳转登录；现有连接器能读项目/组织元数据及日志，不能据此核实当前额度限制。已请求用户自行登录，未索取账号或密码。10月21日具体截止时刻/时区及解除限制状态仍未获证实。
- GitHub 只读 `gh secret list --repo gongyijie85/bookrank --json name,updatedAt` 确认 NYT_API_KEY、GOOGLE_API_KEY 名称存在，PRH_API_KEY 名称缺失。仓库 owner 类型为 User，update-books job 没有命名 Environment；当前本地 workflow 已引用这些名称。未读取任何密钥值，未创建凭据，存在性也不能证明有效性/额度或线上Render注入情况。PRH需另行由用户配置已有有效凭据；缺配置时保持失败状态及旧快照。
- NYT官方公开规格仍列出 /svc/books/v3/lists/names.json，未找到能证明该路径已被替换的官方材料。没有用密钥进行在线探测，因此历史404根因未关闭，不能为了消除告警擅改端点。[NYT官方规格](https://github.com/nytimes/public_api_specs/blob/master/books_api/books_api.yaml)

平台证据只保存筛选后的统计与观察事实：`.scratch/incident-20261021/platform-and-data/platform-readonly-summary.json`、github-secret-names-check.json；未保存密钥或连接串。

### 发布差分依赖

本次故障差分不能直接独立应用到干净HEAD：BookService使用的 DetailCache、失效核心、BookLanguagePack缓存装配及 report_failures 参数来自原有用户补丁。文本可应用不等于导入成功；隔离副本已复现遗漏依赖时 import app 失败。

审计将原有前置单列：detail_cache.py、detail_cache_invalidation.py、book_detail_cache.py、book_language_pack.py相关缓存差分、app工厂缓存装配、BookService report_failures、共享测试缓存清理和对应测试；site workflow 还依赖原有 action 版本改动。未混入UX、模板、static/dist等其他工作。前置组合加故障差分在隔离候选中导入成功、105项缓存/压缩回归通过，但仍须独立审阅与全量门禁，不能自动算作批准发布。

材料见 `.scratch/incident-20261021/release-audit/REVIEW.md`；49文件初次捕获包已明确标成后续源文件发生变化，不能当成最新发布包。精确差分来源、哈希、排除项和捕获局限均保留；CHANGELOG最初已dirty且缺完整before，未混进声称精确的组合patch。

### 显式初始化入口

Procfile 仍引用不存在的 build.py，并在启动时安装依赖，现统一为 `gunicorn -c gunicorn.conf.py run:application`。实际 Render 的 render.yaml 原本指定独立命令，因此此问题不能直接当作线上超时根因。

scripts/init_external_postgres.py 原先在解析参数前导入 run，并默认调用迁移；输出隐藏密码后的完整连接串也不符合本次边界。现在默认只读核验已显式配置的数据库连接与版本，不读取dotenv，不导入生产运行入口，不输出连接串或驱动异常详情。显式 `--upgrade` 仅接受已有合法版本，不推断、删除或补写旧库历史。

空库初始化必须显式 `--bootstrap-empty-schema --schema <预建专用空schema>`。拒绝public/系统schema及所有已有namespace依赖对象，含表、版本、视图、序列、类型、collation、operator。基于已审查当前head，在同一PG事务创建模型、补历史server defaults/普通及GIN索引/pg_trgm、写版本，任一步失败全部回滚；新迁移head变化则先拒绝，要求重新审查基线。未修改迁移历史文件，仍不能保证任意旧版本库都可升级。

`--seed-base-data` 只允许搭配显式写入模式；检查静态结果及基础行数，空/部分失败不会报告成功。种子与schema属于不同事务，失败可保留已提交数据，重试前必须核实。自定义schema应用必须另行审查配置相同search_path；脚本不修改生产配置、权限或Data API授权。README与docs/supabase-migration.md已同步当前命令及验证边界。

新增 tests/test_external_postgres_init.py 先14项失败，最终 **30 passed**，其中15项真实本机PG；另由代码审查代理独立跑同一30项通过。覆盖只读、无副作用导入、脱敏、写入参数门槛、未知版本/对象、显式升级、种子状态、同事务失败回滚。证据 `.scratch/incident-20261021/bootstrap-audit/VALIDATION.md`。该验证没有连接生产，初始化也未在生产执行。

### 后端超时结果与跨入口重提

继续追踪确认：FutureTimeout 只结束等待，真实线程仍可能写库；原逻辑却记录timeout失败并释放上层锁。严格Event复现中，释放原线程前两次同社调用已启动两个worker。手工全量还会无条件标success，自动摘要不推进成功时间，下一次调度能够整批重投。

现在同一应用SyncEngine在公开单社入口预留token，超时包装在提交Future之前占位，真实执行退出/取消才按原token释放；旧done callback不能误清新占位。batch标记覆盖枚举与来源间隙。auto、cron、manual、admin共享在途检查与待核实标记；未知结果保留pending_verification/completion_status=unknown，只记observed_at，不写finished_at或成功时间。worker空闲不是结果已核实；原待核实状态不自动变为成功。

自动摘要中的pending还会阻止后续调度与手工换入口重投；摘要写入失败时，本进程仍保留保护。HTTP cron、管理员爬虫及workflow runner均传递pending状态；submit runner收到后端明确pending时退出2且只提交一次，不能因为顶层success=true就报告accepted。该状态不是普通失败后可自动重投的信号。

20项新增 tests/test_sync_timeout_safety.py 覆盖排队/在途、直接单社并发、异常释放、旧token回调、batch边界、超时后重复请求、线程退出后未知仍拦截、自动摘要保存失败、自动/手工/管理端互换入口、HTTP状态。另补workflow 2项pending回归；先红后绿。独立审查相关271项通过，随后两项测试清理的反序73项通过，最终代码审查没有剩余P1/P2。详细 `.scratch/incident-20261021/timeout-safety/VALIDATION.md`。

**边界：** token、共享内存标记及手工任务槽仍是进程内状态；已持久化的auto pending摘要可跨重启继续阻止，但摘要落库失败或manual/admin-only内存状态不能保证跨实例/重启保护。进程崩溃发生在摘要落库之前也没有持久关联结果。写入型cron仍只发一次，不能据本地保护启用跨进程盲重试。待核实任务须先核对日志、回执及实际数据，再按另行批准的维护流程恢复；本次未清理生产待核实状态，也未自动补跑。

### 第三阶段测试隔离修补与失败保留

- 首轮含24项真实PG整合：3393 passed、13 failed、1 skipped，140.17秒；不是验收通过。8项新HTTP回归受前序测试ADMIN配置污染，显式设置并自动恢复测试ADMIN/CRON配置，鉴权实现与原HTTP断言保留；前序来源健康→新回归组合先8 failed/18 passed，修后26 passed。
- 另5项日志断言为空，根因为真实PG升级测试执行 migrations/env.py 的fileConfig，禁用已注册app logger并替换全局日志配置。仅在初始化测试fixture中保存/恢复root及既有Logger状态；真实fileConfig、DDL、迁移与日志断言均保留，没有修改生产日志配置或屏蔽检查。初始化→抓取日志→后台告警→周报状态同进程57项通过，4条旧get_engine弃用警告。
- 旧test_setup_extended两项直接pop会永久删除session应用的service，反序造成admin测试2失败。仅换成monkeypatch.delitem自动恢复，全部断言保留；反序73项通过。
- 日志隔离首次复核另遇15项PG连接拒绝（42项通过），不是业务断言失败。旧本机测试实例已退出、原启动会话不存在，原因未确认；未修改应用代码。只重新启动已核对路径的自建scratch集群，SHOW data_directory再次匹配后同命令57项通过。新启动控制器使用隐藏窗口与文件重定向并退出0，避免依赖长期保留的输出管道。该基础设施失败单列保留，不计作通过。
- workflow新回归初次存在测试导入与断言放置错误，纠正测试后再取得真实契约2 failed，再修runner达到46 passed；初始与有效red日志均保留，未删除原accepted退出0断言。

本阶段追加触及 app/services/sync_request_gate.py、app/routes/{new_books,api/cron}.py、scripts/init_external_postgres.py、docs/supabase-migration.md、tests/{test_sync_request_gate,test_external_postgres_init,test_sync_timeout_safety,test_setup_extended}.py，并继续修改已列出的sync_engine/setup/admin/workflow/export及对应回归。最终精确差分与原有前置分开列于 `.scratch/incident-20261021/release-audit/stable-3/FILE_LIST.md`。本报告是本次新文件，组合patch包含捕获版；验收后的补充内容另以docs-only差分/hash保存。只有已dirty且缺完整before的CHANGELOG从精确组合patch排除，需按新增段人工复核来源。

## 最终整合验收（2026-10-21）

### 当前工作区与候选组合

| 检查 | 最终实际结果 | 证据 |
| --- | --- | --- |
| 当前工作区全部pytest，Python3.13，开启两个本机PG manifest | **3406 passed、1 skipped、100 warnings，86.19%，137.98秒**；覆盖率门槛70%通过，含24项真实PG | continuation-final/pytest-verified.log |
| 当前工作区Ruff / format | 两项均退出0，278文件已格式化 | ruff-check-verified.log / ruff-format-verified.log |
| 当前工作区mypy app/ | 无额外放宽参数，113源文件，0错误 | mypy-verified.log |
| JS lint / 前端 | npm run lint:js 通过零警告门禁；npm run test:frontend **57 passed** | eslint.log / frontend.log |
| i18n drift | 472条目录同步，退出0；原en两条/zh一条缺译警告保留 | i18n-drift-verified.log |
| translations聚合动作 | pybabel extract→update→compile均退出0，在translations隔离副本运行 | translations-{extract,update,compile}.log |
| 最终候选全部pytest，Python3.13，不启PG opt-in | **2897 passed、25 skipped、12 warnings，84.92%，93.12秒**；70%门槛通过 | release-audit/stable-3全量日志与门禁结果 |
| 最终候选Ruff/format/mypy及四个故障脚本lint/format | 全部退出0；format252文件，mypy110源文件 | stable-3门禁日志 |
| 候选依赖/导入/缓存定向 | 明确前置+故障patch check/apply均0，导入0，105项通过 | stable-3前置与focused日志 |
| git diff --check | 退出0；仅保留既有LF/CRLF提示 | continuation-final/diff-check-verified.log |
| 静态文件保护 | 对审计的10个static/data JSON逐个核对SHA256，全部未改变 | static-json-hashes.json |

表中continuation-final日志均位于 `.scratch/incident-20261021/continuation-final/`。工作区命令如下；执行时专用PG正在运行，现在已停止，不能直接把manifest改指其他数据库：

```powershell
$env:PYTHONPATH='D:\BookRank3\.scratch\incident-20261021\guard'
$env:PYTHONIOENCODING='utf-8'
$env:BOOKRANK_LOCAL_PG_MANIFEST='D:\BookRank3\.scratch\incident-20261021\continuation-pg\active-local-run.json'
$env:BOOKRANK_BOOTSTRAP_PG_MANIFEST=$env:BOOKRANK_LOCAL_PG_MANIFEST
$env:COVERAGE_FILE='D:\BookRank3\.scratch\incident-20261021\continuation-final\.coverage-verified'
.\.scratch\incident-20261021\continuation-py313\venv\Scripts\python.exe -m pytest tests/
```

Lint/格式实际范围是 `app/ tests/ run.py update_books.py scripts/workflow_http.py scripts/check_nyt_category_frequencies.py scripts/init_external_postgres.py`，类型命令为原样 `mypy app/`。其他命令为 `npm run lint:js`、`npm run test:frontend`、`python scripts/check_i18n_drift.py`；翻译使用原babel.cfg、忽略工具目录，输出到本次隔离目录后依次update/compile。未更改门槛、关闭检查、删除有效断言或屏蔽警告。

Windows仍无make：**make check、make i18n-drift原命令未运行**，其lint/type/test/translations动作已逐项执行，drift额外单独检查。唯一工作区跳过是Windows无法创建symlink；候选25项为同一symlink1项+未启manifest的15项初始化PG+9项运行PG，不能把这些skip说成候选真实PG验收。工作区已单独真实执行全部24项；版本为PG18.4，仍未验证目标PG17与Linux/Python3.13/Gunicorn/PG的联合环境。先前Linux8项为Python3.12/SQLite单独运行，不扩大结论。

最终候选是干净HEAD副本+11项明确列出的原有前置+58项故障文件，3路径重叠，共66路径；原有其他页面/静态资源/缓存改动未整包加入。候选比工作区少部分原有模块与测试，故mypy110/113、pytest数量不同。stable-1保留8项鉴权隔离失败及import分组lint失败；stable-2仅做构包/105项检查，因已知fixture修补未运行全门禁；**只有stable-3是本阶段最终已验收代码组合**。代码、测试及其他依赖的65路径无漂移，本报告最后补充独立保存docs-only差分；这不替代发布审查或批准。最终审计见 `release-audit/FINAL_REVIEW.md`，补充文件为 `stable-3/docs-only-after-gates.patch`、`docs-supplement-manifest.json`；均位于本次scratch证据目录，不覆盖已测捕获版。

专用PG结束前再次核对SHOW data_directory与postmaster PID：pg_ctl stop退出0，PID退出，loopback7597明确拒绝新连接，数据目录保留，manifest.started=false。新PID79584只属于本次scratch实例；未停止其他实例或系统服务。原启动会话消失的基础设施失败已在上节单列。Grok/Qoder及Linux进程的前阶段退出记录继续有效。

Git HEAD最终仍为7fc28bb87006a2c1f5feffae3affeabfe2b3658d，分支未切换；最终status保存于git-status-final.txt。原工作区仍有大量用户补丁及本次修改，未提交、推送、创建PR、合并、部署、恢复静态数据或执行生产写入。

### 后续上线顺序与仍需批准的操作

1. **当日平台状态先核实。** 用户完成Supabase控制台登录后读Usage/Billing/Fair Use，确认10月21日实际截止时刻、限制及当前出流量；Render单独核对账单。13.79GB显示不能自行推算最终账单，ACTIVE_HEALTHY不代表额度解除。付费变更、额度申请或支持操作另行批准，本次均未执行。
2. **审查发布组合。** 独立审查11项原有缓存/action前置及58项故障差分，保留用户其他工作。随后在Linux/Python3.13/目标PG17的隔离或预发布环境跑相同门禁、Gunicorn/连接池/迁移与并发验收。保留必需检查和分支保护；push、PR、合并、部署需另行批准。
3. **先发布保护，再验业务。** 迁移先备份并核对当前schema heads，按审查结果显式执行，不能让业务请求修库。分别验证存活、就绪、真实业务数据、异步完成及告警回执；连续观察超时、worker重启、池等待与传输量。当前本地修复未上线，线上仍有首次请求初始化记录，Render根因尚未关闭。
4. **待核实与数据恢复分别处理。** 先查询真实任务日志/批次回执/实际数据，再批准解除待核实保护或补跑。PRH缺配置需用户提供已有有效凭据并单独批准配置操作，本次未创建凭据。历史531c快照需逐源核验及带可信成功时间的候选，经受保护流程发布；本次不恢复。
5. **回滚保持数据保护。** 记录部署前代码、schema heads、配置与快照；后续优化回滚到已验证的保护版本。若需退回缺保护的旧版本，先暂停相应写任务并保留待核实记录，不能借回滚重新启用盲重投、删版本记录或空快照覆盖。数据库向前修复优先，回滚迁移/数据恢复须单独备份、演练和批准。

尚未获证实：Supabase额度解除及截止具体时间/时区、Render超时主因与资源历史、NYT历史404、密钥有效性/Render注入、跨进程完整幂等、历史快照在线真实性与新鲜度、实际生产流量改善比例。查询缓存节省数据库返回流量，浏览器缓存/压缩/响应缩减节省相应Render传输；任何优化都不能撤销本周期已产生用量。
