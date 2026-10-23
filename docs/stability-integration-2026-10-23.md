# BookRank 稳定性修复交付记录

日期：2026-10-23。状态：本地修复候选验证通过，尚未发布，生产数据和流量效果待验收。

## 代码位置与边界

- 候选工作树：`C:\Users\Administrator\.codex\worktrees\bookrank-stability-integration\BookRank3`。
- 基线为本轮只读核对的远端 main：`a86acdbff3a7c61f351bda9e29795dfcf34d529f`。
- 原 `D:\BookRank3` 可访问；未改权限，核对的 105 个原文件哈希保持不变，未清理或覆盖原有修改。
- 没有提交、推送、PR、部署、生产迁移/写入、套餐变更、权限变更或凭据轮换。候选不含任何 `static/data/` 更新。
- 测试使用禁 dotenv、禁止外网的隔离配置。PostgreSQL 为本轮新建的本机集群，连接前核对版本、监听地址和实际数据目录；没有连接生产数据库。

## 根因与修复

| 问题 | 修复后的行为 |
| --- | --- |
| 工作流的超时/异常在业务结果分类前退出；超时不能说明服务端未执行 | 有界读取重试，写任务单次提交；稳定幂等键和数据库持久回执区分受理、运行、完成、失败、跳过、待核实。新增鉴权只读回执查询，未知任务不会启动执行。 |
| 抓取失败被当成空成功，失败时间可能推进成功时间 | 保留有效来源快照和原成功时间；分别记录尝试、来源成功、完整成功及失败。拒绝空数据发布，部分失败不会伪装成全量成功。 |
| 相同读取反复查库，并发未命中重复回源，事务未提交数据可能进入共享缓存 | 命中缓存先返回；同键并发合并，批量语言包/精简字段查询，提交后失效。未提交数据绕过共享缓存；详情快照保留主分支新增的奖项身份字段。 |
| 图片写入和缓存有效性检查不足，压缩协商处理不完整 | 同源请求合并，唯一临时文件完整下载后原子替换，失败保留旧图；保留主分支异步补封面。尊重 `gzip;q=0`，保留多行 Vary 和 304 协商头。 |
| 惰性数据库初始化及迁移失败处理不安全 | 业务请求不执行迁移，失败保留迁移版本记录；存活、数据库版本就绪与业务数据验收分别处理。 |
| 真实 Gunicorn 测试发现生产首次 GET 仍会创建 7 家出版社 | 在公共惰性播种闸门中禁止生产自动播种，覆盖 API、桌面及移动页面；实际 SQL 必须只有 SELECT，零初始化、零提交、零新增行。显式管理员初始化、静态导入和正常抓取同步继续可用。 |
| NYT 404/Google 429、告警正文过长、空导出及受保护分支推送失败 | 上游失败明确报告；Google 采用共享冷却和有限重试，保留有效 key 被 400 拒绝后的单次降级。Issue 正文有长度上限；导出生成候选产物并校验非空，再走受保护分支流程。没有关闭分支保护。 |

这些修复不表示 NYT、Google 或 Supabase 的线上限制已经解除，也不证明真实来源已同步。

## 修改文件

完整路径、原始及 LF 文本哈希见 [最终清单](D:/BookRank3/.scratch/integration-20261023/final-delivery-manifest.json)，补丁见 [main 基线补丁](D:/BookRank3/.scratch/integration-20261023/final-candidate.lf.patch)。主要文件如下：

| 范围 | 文件 |
| --- | --- |
| 同步与回执 | `scripts/workflow_http.py`、`app/services/cron_receipt.py`、`app/routes/api/cron.py`、`app/services/new_book/sync_engine.py`、`app/services/batch_import_service.py` |
| 快照与爬虫 | `update_books.py`、`app/services/publisher_crawler/base_crawler.py`、`google_books.py`、`google_books_publisher.py`、`macmillan.py` 等相关来源 |
| 缓存和数据库读取 | `detail_cache.py`、`detail_cache_invalidation.py`、`book_detail_cache.py`、`award_cover_cache.py`、`public_metadata_cache.py`、`cache_service.py`、`api_utils.py`、书目/推荐/语言包/新书查询服务及相关路由 |
| 初始化与健康 | `run.py`、`app/__init__.py`、`app/setup.py`、`app/services/health_service.py`、`sync_request_gate.py`、`scripts/init_external_postgres.py`、`gunicorn.conf.py`、`Procfile` |
| 发布链路 | CI、监控、HF 恢复/加固、三类 cron 触发、爬取及导出工作流；README、迁移说明和变更记录 |
| 回归 | 同步超时/幂等回执、快照保护、缓存并发/事务/流量、图片、压缩、迁移、生产读取、工作流等测试；保留主分支既有测试及安全断言 |

主分支已有模板和 JS/CSS 未被旧文件覆盖，没有新增生产依赖，没有手改前端构建产物。

## 实际验证

| 环境/命令 | 结果 |
| --- | --- |
| Linux/WSL2 Ubuntu，Astral CPython 3.13.17，Gunicorn 23.0.0，PostgreSQL 17.11；`python -m pytest tests/ --timeout=30`，沿用 70% 覆盖率门禁 | **4025 passed，0 failed，0 skipped，111 warnings，87.15%**；129.86 秒，含 26 项真实 PostgreSQL 用例及 Linux 符号链接检查。 |
| 同一冻结源码，真实 Gunicorn 生产工厂 + 新 PostgreSQL 17 | **11 项检查通过**：worker 内单调度器、存活/就绪、空测试库首次业务读取零播种、纯 SELECT、无惰性迁移、真实 HTTP 压缩协商及 worker 替换。测试库的预期空结果不代表生产业务数据同步成功。 |
| Windows CPython 3.13.0，新 venv 按当前 main 的 requirements 安装；`python -m pytest tests/` | **3998 passed，27 skipped，96 warnings，86.86%**；104.51 秒。26 项 PG 和 1 项 Linux 符号链接在 Windows 跳过，已由上述 Linux 全套实际覆盖。 |
| `ruff check`、`ruff format --check`、`mypy app/` | 全部通过；mypy 检查 114 个文件，零错误。Linux 还检查了修改的启动/同步/迁移脚本。 |
| `npm run lint:js`、`npm run test:frontend` | ESLint 零警告；前端 **383 passed，0 failed，0 skipped**。 |
| `python scripts/check_i18n_drift.py` | en/zh 各 560 条目录同步；保留已有“名/年”两条英文翻译警告，未新增 msgid。 |
| 独立代码审查、Python 审查 | 主体及最后生产读取修复均复核，无未解决发现；最后增量各自 26 项定向测试通过。 |

覆盖了超时重试、相同请求/批次重放、抓取失败保留旧数据、冷缓存并发合并、事务隔离、压缩协商、迁移失败保留版本及成功时间/数据新鲜度。没有以 HTTP 200 或“任务已启动”替代这些断言。

测试冻结清单为 `tested-source-manifest-v3.json`，SHA256：`60075c2d1ba3687aa017426774960f6c0ad84b4628c2567950e0138a99715863`。联合运行前后均核验源码集合和全部哈希；运行后只更新本交付报告、后续安排和变更记录，最终清单另核验所有非文档文件与测试版本一致。

### 保留的失败记录

- 旧独立候选的 23 项失败保留，没有删测试换取通过。当前 main 三方整合补齐依赖，并保留其安全返回路径、异步封面、语言和推荐逻辑。
- 初次 Windows 全套 13 项失败：旧测试配置/页面断言未适配缓存及 main，另有旧 venv 的 Werkzeug 与 main 锁定版本不符；已修复测试配置，并重建隔离 venv 按现有 requirements 对齐，没有改依赖锁定。
- 第一轮 Gunicorn 503 是测试前置把版本表建在另一个 schema，生产连接实际查询 public；就绪检查正确拒绝。修正本地测试前置，没有放宽就绪断言。
- 第二轮 Gunicorn 揭示生产 GET 播种的真实漏洞。先加失败回归，再修公共闸门；新版从完整门禁重新验证。两轮失败日志及诊断均保留。
- 工具准备中的 WSL `/tmp` 生命周期和 DrvFS 符号链接问题单独记录；工具改放专用用户目录，没有安装全局包或修改系统服务。

## 未解决项与安全事项

- Supabase 额度限制的当前状态仍未知，不能按补额度日期或健康检查推定恢复。没有生产同步成功、来源真实数量/新鲜度或流量降幅证据。
- 原静态文件七个来源为空，历史 `total_books=0`，不能作为数据发布候选；本补丁不更新这些文件。发布前须获得有效非空数据或保留可验证的旧有效快照。
- 幂等保证针对相同任务键/批次；不同键、无键旧调用和其他调度入口不构成跨实例全局互斥。未决任务先查原持久回执，不删除回执或盲目换键重提。
- 仓库只有通用 Procfile 注释提到 Railway，未确认部署关联或凭据泄露；没有列出或轮换相关凭据，也没有把 Railway 的数据库处理建议用于 Supabase。
- 上述测试是本地隔离验证，实际 Render/HF 部署版本、生产数据和同口径流量仍需上线后验收。

## 后续上线顺序

1. 单独确认允许的推送、PR、合并及部署范围；此前只保留本地候选。推送前重新核对 main，若变化则重新整合并验证。
2. 只读确认 Supabase 当前限制、实际部署 SHA、迁移版本、来源数量/最后成功时间及未决回执；保存有效快照与上一批准版本的回滚材料。状态未知不反复触发同步。
3. 在 `codex/` 分支提交清单内差分，通过受保护 PR 和必需检查。没有数据验收就不发布数据产物；迁移不匹配时停止，生产迁移/播种须另行明确授权。
4. 获准后按既有 Render 和 main→HF 镜像链路发布，核对实际部署 SHA。HF 重启不能代替代码同步。
5. 核验原任务最终回执、实际来源数量、成功时间和有效快照；在相近业务请求量下比较数据库返回字节、图片回源、响应大小及错误率。未取得证据前保持“生产待验收”。

## 回滚与停止条件

- 任何必需检查失败、空数据、来源结果未知、版本不匹配或 Supabase 仍受限，停止发布，保留旧有效数据与证据。
- 应用恢复上一批准部署 SHA，静态数据恢复事先保存的有效快照及其成功时间。保留数据库、迁移历史和任务回执，不通过删版本号、删回执、自动降级或重复同步来“解锁”。
- 本轮没有修改生产数据库，应用回滚不要求撤销本轮生产迁移。若后续另行批准迁移，必须另备数据库兼容和恢复方案。
- 本地候选与原脏目录隔离；撤销候选按清单处理，不对原目录执行 reset/clean 或批量覆盖。

## 证据位置

- [最终交付清单](D:/BookRank3/.scratch/integration-20261023/final-delivery-manifest.json)：完整文件/哈希、补丁哈希、应用验证和原目录保护结果。
- [Linux 完整门禁](D:/BookRank3/.scratch/integration-20261023/environment/gate-20261023T012602Z-b63f4e3d/result.json)、[pytest 日志](D:/BookRank3/.scratch/integration-20261023/environment/gate-20261023T012602Z-b63f4e3d/pytest.log)、[Gunicorn 结果](D:/BookRank3/.scratch/integration-20261023/environment/gate-20261023T012602Z-b63f4e3d/gunicorn-result.json)。
- [Windows 最终全套](D:/BookRank3/.scratch/integration-20261023/windows-v3-pytest.log)、[前端测试](D:/BookRank3/.scratch/integration-20261023/frontend-tests.log)。
- `D:\BookRank3\.scratch\integration-20261023\environment\gate-20261023T011237Z-fd1290f5` 与 `gate-20261023T011833Z-71ad3bb7`：两次 Gunicorn 失败及诊断，不计作最终通过。

最终测试进程和 PostgreSQL 已停止，端口拒绝连接，本轮候选符号链接已移除；没有设置生产自动重跑或后台发布。
