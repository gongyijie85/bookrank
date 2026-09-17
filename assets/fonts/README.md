# 内置字体（PDF 导出用）

## `wqy-microhei.ttc`

| 项 | 值 |
| --- | --- |
| 字体 | 文泉驿微米黑 / WenQuanYi Micro Hei（TTC，含 Micro Hei 与 Micro Hei Mono） |
| 版本 | `0.2.0-beta`（Debian 打包版本 `0.2.0-beta-4`） |
| 许可 | **Apache License 2.0**（字体 name 表内嵌声明，license URL `http://www.apache.org/licenses/LICENSE-2.0`） |
| 大小 | 5 177 387 字节 |
| sha256 | `2420e8078af796b19a3f6ef13de527a1a91c1e7171eea115926c614ced1009b3` |
| 轮廓 | `glyf`（TrueType；fpdf2 **不支持 CFF/OTF**，换字体时必须保持 TrueType） |
| 覆盖 | GBK 全部汉字（Unicode 5.1 的 U+4E00–U+9FC3），实测 `cmap` 34600 条 |

**来源（未做任何修改）**：Debian 软件包 `fonts-wqy-microhei`，取自国内镜像

```bash
curl -O https://mirrors.tuna.tsinghua.edu.cn/debian/pool/main/f/fonts-wqy-microhei/fonts-wqy-microhei_0.2.0-beta-4_all.deb
# 包内 ./usr/share/fonts/truetype/wqy/wqy-microhei.ttc 即本文件
sha256sum wqy-microhei.ttc   # 应等于 2420e8078af796b19a3f6ef13de527a1a91c1e7171eea115926c614ced1009b3
```

> ⚠️ GitHub 上另有一份同名镜像仓库（`anthonyfok/fonts-wqy-microhei`），其
> `wqy-microhei.ttc` 的 sha256 是 `e4bca8df123ce01b104780f576ea1a58b9a5ff1662a91124b6d3180cb6c88212`，
> **与 Debian 官方版本不是同一构建**。这里选 Debian 版本，是为了来源可追溯、哈希可核对。

## 为什么把字体放进仓库

`ExportService._init_pdf_font()` 找不到 CJK 字体时**不报错**，只把 PDF 文本降级成纯
ASCII（中文变 `?`），调用方完全看不出来。Render 走原生 python 环境（`render.yaml` 的
`buildCommand` 只跑 pip），装不了系统字体包，镜像里也没有任何 CJK 字体——2026-09-17
用公开的导出路由取证，线上周报 PDF 只有 2814 字节、`/BaseFont` 仅 `Helvetica`、
没有 `/FontFile2`，即**中文 PDF 已经坏了很久而无人发现**。

自带一份字体后，PDF 中文不再取决于宿主装了什么：Windows / macOS / Linux / CI /
Render / 容器行为一致。

## 维护约束

- `assets/` **不在** HuggingFace Space 的同步白名单里（见 `.github/workflows/ci.yml`
  的 deploy job，白名单是 `app templates static translations migrations` 等）。Space 上
  的中文字体由 `Dockerfile` 的 `apt-get install fonts-noto-cjk` 提供，两条路互不依赖。
- 字体**不放** `static/`：`static/` 会被同步到 Space，而 HF 的 Xet pre-receive 钩子
  拒收新增二进制文件，会让整个 deploy job 变红。
- 换字体时必须同时更新：`app/services/export_service.py` 的
  `_BUILTIN_FONT_CANDIDATES`、本文件的哈希、以及
  `tests/test_export_service.py` 里断言字体在位且可加载的回归锁。
