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

3. **mypy override 债务清理**
   - 逐步移除 `pyproject.toml` 中不必要的 `disable_error_code`
   - 提升核心模块类型覆盖率
   - 验收标准：mypy 无 override 的模块数量明显增加

4. **低覆盖率模块测试补齐**
   - 识别并优先覆盖核心业务流程中的低覆盖模块
   - 验收标准：整体覆盖率稳定在 80% 以上

5. **N+1 查询回归保护**
   - 为已修复的 N+1 场景增加回归测试或查询断言
   - 验收标准：新增相关测试能捕获回归

6. **翻译质量评估与采样**
   - 建立翻译结果采样机制，定期评估智谱 AI 与备选翻译质量
   - 验收标准：每月至少完成一次人工采样评估

7. **Wiki 同步机制**
   - 建立 Code Wiki 与 GitHub Wiki 的同步流程
   - 验收标准：仓库 Code Wiki/ 更新后，GitHub Wiki 能在一次手动或自动流程后同步

8. **Render 资源阈值告警**
   - 增加内存、响应时间等关键指标监控与告警
   - 验收标准：达到阈值时能通过 webhook 或 Sentry 通知维护者

## 长期方向

- 持续维护依赖安全与性能
- 根据社区反馈调整功能优先级
- 保持代码质量门禁（Ruff / mypy / pytest-cov）通过
