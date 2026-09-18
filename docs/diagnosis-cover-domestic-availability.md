# 封面国内可用性诊断报告（无 VPN 场景）

- 发起：2026-09-18，用户报告「国内部分用户未使用 VPN 时无法加载图书封面」
- 结论：**已定位并修复**，修复 PR #253 → main `13181e8`，生产已验证 GREEN
- 相关文件：`app/utils/cover_urls.py`、`app/services/api_utils.py`、
  `app/services/cover_resolver.py`、`scripts/check_cover_proxy.py`

## TL;DR

浏览器侧**从来没有**直接请求过境外图床 —— SSR、客户端重渲染、移动端三条路径全部已走同源
`/cover?src=…` 代理，所以"挂不挂 VPN"本来对浏览器没有区别。

真正的缺陷在**服务端**：封面要过两道门，而两道门的判据不一致。

| 门 | 位置 | 判据 |
| --- | --- | --- |
| 代理白名单 | `cover_urls.is_allowed_cover_host` | 只看 hostname，http / https 都放行 |
| 下载守卫 | `api_utils._is_safe_image_url` | **额外要求 `scheme == 'https'`** |

Google Books API 的 `imageLinks.thumbnail` **默认返回 `http://books.google.com/…&source=gbs_api`**，
于是这类地址**过了第一道门、被第二道门拒掉**；而拒掉的位置在
`ImageCacheService._enqueue_prefetch()` **之前** → 后台预取从未提交 → 该封面**永远不会进缓存**
→ `/cover` 请求恒返回 302 到占位图，前端重试永远等不到真图。

线上抽检 75 张封面，**5 张永久停在占位图，全部是 `http://` 形态**。

## 证据（按类型分级）

### automated（脚本 / 命令输出，可复现）

| 项 | 命令 | 结果 |
| --- | --- | --- |
| SSR 是否泄漏外链 | 爬 `/` `/new-books` `/awards`（桌面 + 移动 UA），抽 `src`/`srcset`/`data-*`/`poster`/`content`/`url()` | **0 个外部图片域名** |
| 客户端重渲染是否泄漏外链 | 线上真实 `#initial-books-data` 载荷 + 线上真实 `index.*.min.js`，在假 DOM 中跑 `updateBooksOnPage()` | 产出 30 个 URL **全部同源** |
| 硬编码外链 | 全量扫 `static/` + `templates/` 的境外图床字面量 | 仅注释与页脚链接 |
| 修复前封面可用性 | `python scripts/check_cover_proxy.py --limit 50` | RED：热缓存 45 / **永久占位 5**（全部 `http://`） |
| 修复后封面可用性 | `python scripts/check_cover_proxy.py` | **GREEN**：热缓存 71 / 冷缓存已收敛 4 / **永久占位 0**（共 75 张） |
| 修复后定点复验 | 对 3 张原卡死封面连探两轮 | 第 1 轮 302 → 第 2 轮 **200 + 真实字节**（12007 / 17884 / 12657，`x-cover-source: cache`） |
| 单测 | `ruff check` / `ruff format --check` / `mypy app/` | 全绿 |
| 单测 | `pytest tests/ -m "not slow"` | **2997 passed, 1 skipped** |

### engine-rendered（服务端返回的响应头 / 字节，非人工观察）

- 命中缓存时 `/cover` 返回 `X-Cover-Source: cache` + `Cache-Control: public, max-age=604800`
  并直接下发 JPEG 字节（不是 302）。
- 未命中时返回 `302 → /static/default-cover.png` + **`Cache-Control: no-store`**
  （失败结果不做长缓存，避免一次抖动把封面长期锁死）。

### manual / 未在本机确证

- **本机无法复现"被墙"**：该机器即便 `curl --noproxy '*'` 也能直连
  `static01.nyt.com`（Fastly 151.101.129.164，0.4s）。且 shell 里默认配了
  `HTTPS_PROXY=http://127.0.0.1:1339`，响应头里会出现 `HTTP/1.1 200 Connection Established`
  —— **代理环境下"直连可达性"测试全部失真**，所以本报告**没有**把"境外图床在国内不可达"
  作为已验证事实，只把它当作设计前提（代码注释与 CSP 白名单都以此为前提）。
- 未在真实无 VPN 的国内浏览器里做端到端截图验证（验证步骤见下，可由用户在网络环境里执行）。

## 为什么这个缺陷难以发现

1. **SSR HTML 看起来完全正常**：里面永远只是 `/cover?src=…`，判不出对错。
2. **日志只有一行 warning**：`Blocked unsafe image URL (SSRF guard)`。
3. **前端重试掩盖了大部分情况**：`cover.js` 按 0.8/2/5/12s 重试，
   正常冷缓存会在几秒内收敛，所以只有"预取从未入队"这一类才会**永久**卡住。
4. **只在真机请求时可见**：必须"请求一次 `/cover` + **间隔复探一次**"才能区分
   "冷缓存但收敛"（正常）与"永久占位"（坏）。

## 修复

`normalize_cover_url()` 作为单一真相源，只做 scheme 升级（不补默认值、不改 path/query ——
Google Books 的查询串一旦被改写就返回 400），在三处调用：

| 位置 | 作用 |
| --- | --- |
| `cover_src()` | 下发边界：`/cover?src=` 里一律是 `https%3A…` |
| `ImageCacheService.get_cached_image_url()` / `_download_to_cache()` | 保证缓存键（md5）、下载请求、SSRF 守卫看**同一个字符串**（幂等，两个入口都加；否则同一张图的两种写法会落到两个缓存键、重复下载两份） |
| `CoverResolver.resolve()` | 写入边界：新落库的 `cover_original_url` 不再带 http |

**守卫本身不改**：`_is_safe_image_url` 的 https 要求属 SSRF 防护，放宽的收益远小于风险 ——
归一化在**上游**解决同一问题。

**存量数据不回填**：DB 里已有的 `http://` 值在渲染与下载两个边界都会被归一化，无需迁移。

## 回归锁

- `tests/test_cover_urls.py::TestGateParity` —— **两道门必须一致**：白名单放行的每个域名，
  http/https 两种形态都要能过下载守卫；同时反向钉住守卫仍拦内网 / 回环 / link-local /
  非 443 端口，白名单仍拦非白名单主机（防止日后把两道门合并或放宽）。
- `tests/test_api_utils.py` —— 白名单 http 封面必须进入预取、下载用 https、
  两种写法共用同一缓存键。**修复前这 3 条红**。

## 修复后如何验证国内环境

### 方式一：代理可用性自检（无需浏览器）

```bash
make check-covers                                   # 打生产
python scripts/check_cover_proxy.py --base http://127.0.0.1:5000   # 打本地
```

输出"热缓存 / 冷缓存但收敛 / 永久占位"三态 + RED/GREEN 退出码。
判据：**永久占位必须为 0**。注意**首次 302、复探 200 是正常**（`block=False` 设计），
只有反复 302 才是坏。

### 方式二：浏览器屏蔽境外域名（最接近真实无 VPN 环境）

1. 打开目标页（`/`、`/new-books`、`/awards`）；
2. F12 → Network → 勾选 **Block request domain**，加入
   `static01.nyt.com`、`storage.googleapis.com`、`books.google.com`、
   `books.googleusercontent.com`、`covers.openlibrary.org`、`images.penguinrandomhouse.com`；
3. 硬刷新（Ctrl+Shift+R）。

**通过标准**：
- 封面**照常显示**（屏蔽境外域名不应有任何影响 —— 这是本设计的验收标准）；
- Network 面板过滤 `Img`，**看不到任何对境外域名的请求**；若看到，说明有渲染路径绕过了
  `cover_src`，需要按 §"渲染路径要数全"继续排查。

### 方式三：真机国内网络

直接用未挂 VPN 的国内网络访问，观察新书速递 / 获奖书单页封面是否为占位图。
首次访问（部署后缓存为空）允许先出现占位图再自动切换为真图；**停留 15 秒后仍为占位图**
即为异常，配合方式一取证据。

## 已知特性（非缺陷）

- **Render 免费层临时盘在每次部署/重启后清空** → 所有封面瞬间变冷，
  首屏必然先占位图、再靠"后台预取 + 前端重试"收敛。每日 `_cover_prefetch_task` 与懒预取负责预热。
  因此**部署后立刻跑自检会看到大量"冷缓存"**，属预期。
- `/cover` **不做同步回源**是硬要求而非优化：首页一屏 15 张封面，生产 workers=1 / threads=2，
  同步回源在上游变慢时会占满全部线程、拖垮整站。

## 后续可做（未在本次范围）

- 移动端首页卡片只有 JSON-LD 里的 `isbn`，从不显示明文 ISBN，与桌面端不一致（既有布局差异）。
- 可考虑给"守卫拒绝"补一条**结构化指标**（当前仅 warning 日志），
  让"被静默拒掉的封面比例"可观测，而不是等用户报障。
