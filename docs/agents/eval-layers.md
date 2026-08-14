# 分层评测 — BookRank 工程与 Agent 侧评测规范

本文件定义本仓库的分层评测结构：每一层一道门，不用一层评全部。

## 四层结构

### L1 单元层（模块接口）
- 范围：模块接口 = 测试面（codebase-design 词汇：测试跨的 seam 就是接口）。
- 门：pytest tests/ 全量 + ruff check + mypy app。
- 例子：test_sync_engine.py（mock 适配器，按能力声明确认引擎行为）、
  test_ingestor.py（入库规则直测）。

### L2 集成层（路由 + 真实 DB fixture）
- 范围：Flask 测试客户端 + conftest 的内存 SQLite（每用例建表/删表隔离）。
- 门：关键路由必须有“异常降级仍 200/4xx”用例，例如
  test_main_routes_extended.py 的新书页各段查询独立降级测试。
- 反模式提醒：patch 目标必须是真实存在的 seam（见 tests/regression-suite.md 约定）。

### L3 端到端冒烟层（关键路径）
- 范围：应用启动 → 健康检查 → 新书列表/详情 → 同步触发 → 周报/导出，
  对应 .github/workflows 的 wake/auto_sync 链路。
- 门：发布前手工/CI 冒烟；CI 中 production-monitor.yml 为运行期监控。

### L4 行为测量层（只测量、不改变行为）
- 范围：date_filter_stats（分类拒绝计数）、source_health（数据源健康）、
  同步摘要（last_auto_sync_result）。
- 门：测量字段有断言（如 counters 六类计数），且证明“测量不改变收录/拒绝行为”
  （test_date_filter_counters.py::test_is_recent_book_stays_isomorphic）。

## 评测集配比（数据侧）

- 常见路径：常规输入、默认参数 → 覆盖率高，防回归。
- 长尾路径：冷门输入、边界日期、缓存丢失、限流降级 → 目标是**不漏**。
- 对抗用例：公式注入、坏 ISBN、异常 JSON、占位日期 → 安全与解析健壮性。

## 检索/推荐侧原则：召回放宽，重排收紧

- 召回层（smart_search/推荐候选生成）宁多勿漏：长尾查询先保证候选进池。
- 重排层（相关性/新鲜度排序）收紧精度：只在这里做精确排序。
- 评测指标分开：召回率@K 评召回层，NDCG/点击评重排层，不混用单一指标。

## Agent 系统评测（若引入 agent 编排）

- 能力评测：单工具/单步正确率（对给定输入，工具选择与参数是否正确）。
- 轨迹评测：端到端任务完成率（对给定目标，完整轨迹是否达成）。
- 两套分数分开出，不合并；能力分解释轨迹分的失败来源。

## 推进门

- 阶段推进用 gate-check 思路：L1/L2 全绿才进 L3/L4；任何一层失败不得“用上一层掩盖”。
- 修复后必须复跑验证命令并留下证据（verification-before-completion）。
