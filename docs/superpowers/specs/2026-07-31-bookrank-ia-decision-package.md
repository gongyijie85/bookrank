# BookRank 产品信息架构决策包

> 来源:wayfinder 地图 [#55](https://github.com/gongyijie85/bookrank/issues/55),由子票 [#56](https://github.com/gongyijie85/bookrank/issues/56)–[#64](https://github.com/gongyijie85/bookrank/issues/64) 的决议汇总而成。收官票:[#65](https://github.com/gongyijie85/bookrank/issues/65)。
> 覆盖范围:约 2–3 个版本 / 3–6 个月产品面。**本文档不交付实现代码**,仅给出方向与优先级;P0 首页部分的实现 spec 见 [#66](https://github.com/gongyijie85/bookrank/issues/66)。

## 1. 导航层级(已锁定的框架)

- 主导航维持五栏,明确信息层级:**首页**=畅销发现;**奖项/新书**=深度发现;**出版社**=入口;**周报**=解读;**关于**=次要
- P0 主战场:首页 / NYT 畅销榜
- 非首页大致优先顺序:获奖书单 → 新书速递/出版社 → 周报
- 移动端与桌面同一套栏目层级与优先级,仅交互形态可不同
- 拓展边界:加深现有发现路径,不加新一级栏目;行业向工具(ONIX/CSV 等)不主导本包(归战略地图 [#41](https://github.com/gongyijie85/bookrank/issues/41))

## 2. 各栏目优化方向

### 2.1 全站现状盘点 — [#56](https://github.com/gongyijie85/bookrank/issues/56)
桌面 5 栏 vs 移动 4 栏不同级;新书速递/搜索移动端有缺口;首页高级筛选仅后端存在,UI 未暴露。详见 `research/issue-56-ia-inventory.md`。

### 2.2 首页 NYT 分类信息架构 — [#57](https://github.com/gongyijie85/bookrank/issues/57)
13 个分类(19 减去纸电合并 2、有声书 4),按体裁分 6 组,组内精装/平装平级并列,默认精装小说,每周/每月更新徽章标注。原型见 issue 内链接。

### 2.3 首页列表与卡片发现体验 — [#58](https://github.com/gongyijie85/bookrank/issues/58)
网格/列表、卡片字段清单均维持现状。新增 P1 原则「数据新鲜度需可见」(`is_cached` 死代码待修)。详情页跳转维持整卡+同标签页,URL 稳定性隐患记 P2。顺带发现 Render 部署缺口(`RENDER_DEPLOY_HOOK_URL` secret 缺失)与 HF Space 备用部署。

### 2.4 首页搜索角色 — [#59](https://github.com/gongyijie85/bookrank/issues/59)
首页内功能不做并列入口。范围扩大到全部 13 个 NYT 分类(忽略当前分类筛选,结果标注来源分类)。建议词维持仅当前分类。P0 含移动端首页新增搜索入口(现状为 0)。

### 2.5 获奖书单 — [#60](https://github.com/gongyijie85/bookrank/issues/60)
以「奖项」为主发现轴,年份为次级筛选。筛选维度类别优先于年份(新增类别筛选 UI,服务层已支持)。移动端本轮补齐类别筛选(P1),年份筛选留 P2。与首页畅销榜/新书速递的交叉发现本轮不承诺(需全新跨模型 ISBN 匹配基础设施,另起 idea)。奖项数量扩张与用户评分/评论划入 Out of scope。

### 2.6 新书速递与出版社 — [#61](https://github.com/gongyijie85/bookrank/issues/61)
出版社页确认为「导航枢纽」(外部目录,维持现状)。新书速递主路径为「时效性」(days 窗口),类别/出版社为辅助筛选。双向跳转维持页面级(不做记录级深度链接),移动端需补齐缺失的跳转。「刚上市」时效徽章本轮定为 P1;翻译状态(是否已出中文版)本轮不决策,需新数据基础设施。

### 2.7 周报(解读层) — [#62](https://github.com/gongyijie85/bookrank/issues/62)
定位「首页附属解读层」,保留独立导航但分类集需跟随首页 `CATEGORIES` 同步(P1,修复现状硬编码 8 类脱节于 #57 的 13 类)。优化优先级详情页 > 列表页(P1)。详细分析板块延伸 #57 每周/每月徽章原则标注月度分类条目(P2)。

## 3. 跨页能力 — [#63](https://github.com/gongyijie85/bookrank/issues/63)

首页 P0 跨页能力最小集:
- **语言切换、主题切换**:已达标,无需改动
- **收藏、分享、导出**:均不进首页 P0(分享维持现状、导出不新增、收藏不修复)
- **发现的 bug**:首页收藏(localStorage)与获奖书单等页面收藏(服务端 session)是两套不同步的实现,但当前无实际使用量,不排优先级,去留留待未来评估

## 4. 拓展候选优先级 — [#64](https://github.com/gongyijie85/bookrank/issues/64)

已排除「奖项↔榜单串联」(#60 已决定本轮不做)。其余候选:
- **相关书/同榜追踪(获奖书单侧)= P1** — 后端 `RecommendationService` 已现成,只差模板接入
- **相关书/同榜追踪(NYT 畅销榜侧)= P2** — 需照现有模式新写一套
- **跨栏目跳转标准化 = P2** — 提炼共享导航宏,消除多模板各自手写的重复
- **榜单历史对比 = 边界内暂不排期** — 无任何现成基础设施;NYT 官方 Books API 已于 2025-05-15 下线 best-sellers history 服务(经官方 Swagger 规范确认,非账号权限问题),无外部数据源退路,只能自建历史表

## 5. P0–P2 总表

| 栏目 | 决策项 | 优先级 | 理由 | 来源票 |
|---|---|---|---|---|
| 首页 | 分类扩展至 13 类,6 组精装/平装并列 | P0 | 覆盖完整 NYT 榜单,匹配图书销售从业者选品逻辑 | [#57](https://github.com/gongyijie85/bookrank/issues/57) |
| 首页 | 搜索扩大到全部 13 分类 + 移动端搜索入口 | P0 | 移动端现状为 0,搜索范围与展示内容对齐 | [#59](https://github.com/gongyijie85/bookrank/issues/59) |
| 首页 | 数据新鲜度可见(修 `is_cached` 死代码) | P1 | 用户需知道数据是否为缓存 | [#58](https://github.com/gongyijie85/bookrank/issues/58) |
| 首页 | 详情页 URL 稳定性(`loop.index0` 隐患) | P2 | 非当前故障,风险项 | [#58](https://github.com/gongyijie85/bookrank/issues/58) |
| 获奖书单 | 移动端补齐类别筛选 | P1 | 类别筛选是本轮核心决策,移动端不跟进则决策落空 | [#60](https://github.com/gongyijie85/bookrank/issues/60) |
| 获奖书单 | 移动端补齐年份筛选 | P2 | 历史遗留缺口,优先级较低 | [#60](https://github.com/gongyijie85/bookrank/issues/60) |
| 新书速递 | 「刚上市」时效徽章 | P1 | 数据已现成,纯模板层工作 | [#61](https://github.com/gongyijie85/bookrank/issues/61) |
| 新书速递/出版社 | 移动端出版社页补齐跳转链接 | P1 | 修复遗漏,与桌面端保持一致 | [#61](https://github.com/gongyijie85/bookrank/issues/61) |
| 周报 | 分类集与首页 CATEGORIES 同步 | P1 | 修复架构漂移,避免 #57 扩容后周报静默过期 | [#62](https://github.com/gongyijie85/bookrank/issues/62) |
| 周报 | 优化优先级详情页 > 列表页 | P1 | 解读价值集中在详情页 | [#62](https://github.com/gongyijie85/bookrank/issues/62) |
| 周报 | 详细分析延伸每周/每月徽章标注 | P2 | 避免把复用数据误当本周变化 | [#62](https://github.com/gongyijie85/bookrank/issues/62) |
| 拓展 | 相关书/同榜追踪(获奖书单侧接入既有服务) | P1 | 后端零成本,模板层小工作量 | [#64](https://github.com/gongyijie85/bookrank/issues/64) |
| 拓展 | 相关书/同榜追踪(NYT 畅销榜侧新实现) | P2 | 需新写逻辑,架构可复用 | [#64](https://github.com/gongyijie85/bookrank/issues/64) |
| 拓展 | 跨栏目跳转标准化(共享导航宏) | P2 | 一致性/防止未来再漏,非新增能力 | [#64](https://github.com/gongyijie85/bookrank/issues/64) |
| 拓展 | 榜单历史对比 | 边界内暂不排期 | 无基础设施,NYT 官方 API 已下线相关服务 | [#64](https://github.com/gongyijie85/bookrank/issues/64) |
| 跨页 | 语言/主题切换 | 已达标 | 全站统一,无缺口 | [#63](https://github.com/gongyijie85/bookrank/issues/63) |
| 跨页 | 收藏/分享/导出 | 不进 P0/P1/P2 | 收藏有 bug 但无使用量;分享现状够用;导出非首页必需 | [#63](https://github.com/gongyijie85/bookrank/issues/63) |

## 6. Not yet specified

- 各栏目优化方向敲定后的验收口径粒度(是否写入决策包正文或另拆实施票)
- 导航文案/图标是否微调(在层级锁定后再定)
- 与 v1.0 技术债票 [#9]–[#16] 的实施穿插顺序(本包只到优先级,不排 sprint)
- 加深发现路径中具体机制(跨榜跳转、相关书等)的交互保真度(待拓展票展开)
- 获奖书单与首页/新书速递的跨页交叉发现(需新增 ISBN 匹配基础设施,建议另开 idea/map)
- 新书「翻译状态」(是否已出中文版)标识(需新数据字段与数据源,建议另开 idea)
- 收藏功能的去留(首页 localStorage 实现与获奖书单等页面服务端 session 实现不同步,当前无实际使用量,是否修复/统一/移除留待未来评估)
- 榜单历史对比若未来推进:NYT 官方已下线 history 服务,无外部数据源退路,只能自建历史表

## 7. Out of scope

- 本 effort 不实现功能代码、不改线上模板/路由(P0 首页部分的实现已另拆为 spec [#66](https://github.com/gongyijie85/bookrank/issues/66))
- 行业向导出/对接(ONIX、多平台 CSV 等)— 归战略地图 [#41](https://github.com/gongyijie85/bookrank/issues/41) 及其子票
- Pro 商业化 MVP — 见战略地图 Out of scope
- 管理端、公开 API、后台任务作为「并列栏目」排优先级
- 新增一级主导航栏目
- 获奖书单的奖项数量扩张(数据运营问题,非 IA 问题)
- 用户评分/评论功能(需全新用户账号与内容审核子系统)
- 出版社静态目录与新书速递 DB 数据的打通(两套数据保持独立,不做记录级深度链接)
- 首页新增导出功能;收藏功能修复/统一(无实际使用量,不投入本轮工程)
