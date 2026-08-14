# 回归测试套件索引

每个生产 bug 修复必须带回归测试；本文件是按“缺陷 → 锁定它的测试”的索引。
新增回归时在此登记一行。

## 约定

- 回归测试必须能**在修复被回退时变红**——尽量走真实路径、少用 mock 掩盖缺陷
  （反例：曾用 patch(..., create=True) 给不存在的幽灵方法兜底，导致
  admin 分类清理端点 500 而测试全绿）。
- 长尾 bug（罕见输入、边界日期、缓存丢失）也登记：目标是“不漏”，不是精确命中。

## 索引

| 缺陷 / 修复 | 回归测试 | 锁定内容 |
|---|---|---|
| admin 清理端点幽灵 _sanitize_category（b35730b 修复） | tests/test_admin_routes.py::TestCleanupCategories::test_cleanup_with_real_sanitize_detects_marketing_category | 不 patch、走真实 sanitize 的分类清理路径 |
| init_publishers 迁移不落库（工单 #88） | tests/test_publisher_manager.py::test_init_publishers_migrates_prh_to_official_api_crawler 等 | 迁移结果经 expire_all 从库重读，必须 commit |
| 同步空结果被误记成功 | tests/test_sync_engine.py::test_sync_with_empty_crawler | total==0 → empty/failure 语义 |
| 单家出版社同步挂死拖垮整批 | tests/test_sync_engine.py::TestSyncPublisherWithTimeout | 600s（测试中 0.2s）熔断路径 |
| PRH 无 API Key 阻塞其余出版社（工单 #86） | tests/test_sync_engine.py::test_prh_api_crawler_without_api_key_returns_none | api_key_required 快速失败 |
| Google Books 日期过滤漏报代价（工单 #83） | tests/test_date_filter_counters.py | 六类拒绝计数，只测量不改变行为 |
| 批量导入重复执行产生脏数据（工单 #134） | tests/test_batch_import.py::test_identical_batch_is_idempotent | batch_id 幂等 |
| CSV 公式注入（v0.9.68） | tests/test_new_books_routes.py::test_export_csv_returns_csv_with_injection_safe_content 等 | 前缀单引号转义 |
| 封面缓存文件在生产重启后丢失（6b7b633） | tests/test_award_cover_sync_service.py::test_cache_path_file_not_exists | 文件存在性探测路径 |
| 出版 30 天内“新书”标准（维护者决议） | tests/test_query_service.py::test_get_new_books_filters_by_publication_date | 出版日期窗口 + 14 天预告宽限 |

## 待补（候选流水线产出后登记）

- 候选 #7 死适配器删除 → legacy 爬虫测试删除记录
- 候选 #3 分类清洗单一归属 → 迁移/清理共例回归
- issue #154 装配失败降级 → 故障注入回归
