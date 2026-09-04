# BookRank 路线图

> 本文档记录 BookRank 的阶段性目标与验收标准。详细变更请查看 [CHANGELOG.md](./CHANGELOG.md)。

## v0.9.84 — 社区基础与一致性（当前重点）

**目标**：补齐开源社区标准文件、仓库展示、Docker 一键运行和 GitHub 社区能力，使社区成熟度达到 100%。

**验收标准**：

- [x] 添加 MIT `LICENSE`、CONTRIBUTING.md、SECURITY.md、CODE_OF_CONDUCT.md
- [x] 添加 Issue Forms、PR 模板、Dependabot 与 CodeQL 配置
- [x] 修复 Dockerfile 引用已删除 `build.py` 的问题
- [x] 提供单服务 `compose.yaml`，支持 `docker compose up` 一键启动
- [x] 修复 Issue #8：NYT 频率检查在已安装项目依赖后执行
- [x] 修正 README badge、License 与在线链接
- [x] 更新 CHANGELOG/VERSION 到 v0.9.84
- [x] 合并 PR 后创建 `v0.9.84` tag 与 Release
- [x] GitHub Community Profile 达到 100%

## v1.0 — API 规范、爬虫可靠性与技术债务

**目标**：在保持现有功能稳定的前提下，完成机器可读 OpenAPI、提升爬虫可靠性、降低类型与测试债务，为正式 1.0 做准备。

**关键方向**：

1. **OpenAPI 规范与文档**
   - 为公开 API 生成并发布 OpenAPI 3.x 文档
   - 使用 Pydantic 模型统一请求/响应验证
   - 验收标准：`/openapi.json` 可访问且通过校验

2. **出版社爬虫选择器漂移监控**
   - 增加选择器健康检查与告警
   - 记录漂移历史，便于快速定位
   - 验收标准：爬虫选择器失败时能在 24 小时内通过 CI 或告警感知

3. **mypy override 债务清理** ✅（2026-09-04 完成，commit ddccb23/869def4）
   - 逐步移除 `pyproject.toml` 中不必要的 `disable_error_code`
   - 提升核心模块类型覆盖率
   - 验收标准：mypy 无 override 的模块数量明显增加
   - 现状：25+ 模块零 override；`mypy app/` 0 errors / 99 files；仅 8 个 ORM 密集文件豁免 SQLAlchemy 2.0 py.typed 噪音。GitHub #10 已关闭。

4. **低覆盖率模块测试补齐** ✅（2026-09-04 完成，整体 84%）
   - 本轮补齐 6 个 0% 模块：category_cleanup 100%、source_control 85%、
     free_translation 91%、pilot_gate 88%、source_health（状态机 8 测试）、
     source_alert 66%（HTTP client mock 边界）
   - 整体覆盖率 81% → 84%，稳定 ≥80% 验收达成
   - 新增 N+1 回归保护（#5）同批次落地

5. **N+1 查询回归保护** ✅（2026-09-04 完成，commit 52d285f）
   - 为已修复的 N+1 场景增加回归测试或查询断言
   - `tests/test_n_plus_one_regression.py`：SQLAlchemy SELECT 计数器断言
     `get_award_books` / `search_award_books` 访问 book.award 时 ≤3 查询
   - 验收标准：新增相关测试能捕获回归（已达成——移除 selectinload 即失败）

6. **翻译质量评估与采样**
   - 建立翻译结果采样机制，定期评估智谱 AI 与备选翻译质量
   - 验收标准：每月至少完成一次人工采样评估

7. **Wiki 同步机制**
   - 建立 Code Wiki 与 GitHub Wiki 的同步流程
   - 验收标准：仓库 Code Wiki/ 更新后，GitHub Wiki 能在一次手动或自动流程后同步

8. **Render 资源阈值告警**
   - 增加内存、响应时间等关键指标监控与告警
   - 验收标准：达到阈值时能通过 webhook 或 Sentry 通知维护者

9. **前端资源打包与指纹化**（GitHub #177）— **核心完成**（commit 6a6180c）
   - esbuild 打包 CSS（5→1，119KB→15.7KB）+ JS 逐文件 minify（93KB→51KB），产物提交 `static/dist/`（Render 生产无 node 构建步骤）
   - `dist_url()` Jinja 辅助：读 manifest.json 返回指纹文件名；无产物时回退源文件
   - 模板全量迁移 dist 引用；CI 前置 `node scripts/build_frontend.mjs`
   - 待实施：CSS 选择器去重（tokens.css 合并、purgecss）、CSP CDN 白名单复核

10. **封面下载异步化与后台预取** ✅（2026-09-04 完成，commit e7934f6，GitHub #178）
    - `get_cached_image_url` MISS 时立即返回占位 + 后台预取（同 URL 去重）
    - APScheduler 每日预取 job；默认封面压缩 <50KB（实际 93KB，-78%）
    - 验收标准：请求线程无阻塞下载，首屏 TTFB 不含图片网络等待

## 长期方向

- 持续维护依赖安全与性能
- 根据社区反馈调整功能优先级
- 保持代码质量门禁（Ruff / mypy / pytest-cov）通过
