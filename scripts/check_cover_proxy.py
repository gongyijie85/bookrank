"""封面可用性自检：判断"国内不挂 VPN 的用户能不能看到真封面"。

## 为什么需要这个脚本

`/cover` 是**同源代理**（见 app/routes/main.py:cover_proxy）：浏览器只请求本站，
由服务端回源到境外图床并落盘缓存。所以判断封面是否可用，不能只看 SSR HTML
（那里永远是 `/cover?src=…`，看不出对错），必须**真的请求一次 `/cover`** 看它回的是
图片字节还是占位图。

设计上 `/cover` 是 `block=False`：缓存 MISS 时立刻 302 到 `default-cover.png`
（并带 `no-store`），由后台线程回源落盘，靠前端 `static/js/cover.js` 按
0.8/2/5/12s 重试等到真图。因此"第一次 302、过一会再请求 200"是**正常**的；
"反复请求一直 302"才是坏 —— 那说明后台预取从未成功，用户看到的是永久占位图。

已知会落入这个坑的一类值：`http://` 开头的封面源。图片缓存下载守卫
（app/services/api_utils.py:_is_safe_image_url）只允许 https，
而 Google Books API 的 `imageLinks.thumbnail` 默认返回
`http://books.google.com/…&source=gbs_api`。守卫的拒绝发生在提交后台预取**之前**，
于是这类封面永远只是占位图 —— 修复见 app/utils/cover_urls.py:normalize_cover_url。

## 用法

    python scripts/check_cover_proxy.py                     # 自检生产（默认宽松，适合本地）
    python scripts/check_cover_proxy.py --base http://127.0.0.1:5000
    python scripts/check_cover_proxy.py --attempts 3 --wait 4   # 定时监控用（更少误报）
    python scripts/check_cover_proxy.py --distinguish-upstream  # 区分"代理坏"与"上游没有图"

退出码：0 = 没有"代理侧永久不可用"的封面；1 = 存在（RED）。

## 两种"永久占位"要分开

- **代理侧**（`--distinguish-upstream` 打开时标为 `stuck-proxy`）：上游能取到图，
  但 `/cover` 始终只有占位图 → 代理/守卫/缓存的问题，**必须修**，计入 RED。
- **上游侧**（`stuck-upstream`）：连源站本身都取不到图（下架、无封面）→ 数据问题，
  不是代理 bug，只计 WARN，避免把"某本书本来就没图"当成故障天天告警。

不开 `--distinguish-upstream` 时无法区分，全部按 `stuck` 计入 RED（本地默认，宁可严格）。

## ⚠️ 运行环境要先自证

本脚本只请求本站 `/cover`，所以结果与你的网络所在地无关 —— 这正是要点
（浏览器同样只请求本站）。但带上 `--distinguish-upstream` 时会直连源站做区分，
而**公司/运营商级代理会让直连测试失真**（curl 会打出 `HTTP/1.1 200 Connection Established`），
那种情况下"上游不可达"的结论不可信。
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse

PAGES: tuple[str, ...] = ('/', '/new-books', '/awards')
DESKTOP_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)
COVER_SRC_RE = re.compile(r'/cover\?src=([^"\'\s>]+)')
DEFAULT_COVER = '/static/default-cover.png'
MIN_REAL_IMAGE_BYTES = 1024  # 与 app/services/api_utils.py:MIN_IMAGE_BYTES 同口径


def _curl(url: str, body_path: str, timeout: int = 30, headers: bool = False) -> tuple[int, dict[str, str]]:
    """GET 一次，返回 (http_code, 响应头)。用 curl 而不是 urllib：

    urllib 默认跟随 302，会把"回落占位图"伪装成 200，正好抹掉我们要测的信号。
    """
    cmd = ['curl', '-s', '-o', body_path, '--max-time', str(timeout), '-w', '%{http_code}']
    if headers:
        cmd += ['-D', body_path + '.hdr']
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    info: dict[str, str] = {}
    if headers:
        try:
            with open(body_path + '.hdr', encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        info.setdefault(key.strip().lower(), value.strip())
        except OSError:
            pass
    try:
        info['_bytes'] = str(os.path.getsize(body_path))
    except OSError:
        info['_bytes'] = '0'
    try:
        return int(result.stdout.strip() or 0), info
    except ValueError:
        return 0, info


def _serves_real_cover(code: int, headers: dict[str, str]) -> bool:
    """这一次响应是不是"真封面字节"（而不是 302 占位图）。"""
    if code != 200:
        return False
    if headers.get('x-cover-source') == 'cache':
        return True
    # 兼容将来去掉该响应头的情况：200 + 图片类型 + 够大，也算拿到真图。
    ctype = headers.get('content-type', '')
    try:
        size = int(headers.get('_bytes') or '0')
    except ValueError:
        size = 0
    return ctype.startswith('image/') and size >= MIN_REAL_IMAGE_BYTES


def collect_cover_sources(base: str, workdir: str) -> list[str]:
    """从若干列表页收集去重后的封面源地址。"""
    ordered: list[str] = []
    seen: set[str] = set()
    page_path = os.path.join(workdir, 'page')
    for page in PAGES:
        code, _ = _curl(base + page, page_path)
        if code != 200:
            print(f'  ! {page} 返回 {code}，跳过')
            continue
        with open(page_path, encoding='utf-8', errors='replace') as fh:
            html = fh.read()
        for raw in COVER_SRC_RE.findall(html):
            source = urllib.parse.unquote(raw)
            if source not in seen:
                seen.add(source)
                ordered.append(source)
        print(f'  {page}: 累计 {len(ordered)} 个不同封面源')
    return ordered


def probe_cover(base: str, source: str, workdir: str, wait: float, attempts: int) -> tuple[int, dict[str, str]]:
    """请求 /cover，最多尝试 attempts 次；任一次拿到真图即算通过。

    返回最后一次的 (http_code, 响应头)。冷缓存收敛需要时间（后端预取 + 前端重试窗口
    约 20s），所以单次失败不足以判死 —— 这也是"误报"的主要来源。
    """
    url = base + '/cover?' + urllib.parse.urlencode({'src': source})
    body = os.path.join(workdir, 'body')
    last: tuple[int, dict[str, str]] = (0, {})
    for attempt in range(attempts):
        if attempt:
            time.sleep(wait)
        code, headers = _curl(url, body, headers=True)
        last = (code, headers)
        if _serves_real_cover(code, headers):
            return last
    return last


def upstream_has_image(source: str, workdir: str) -> bool:
    """直连源站，判断该封面在上游本身是否可取到（区分"代理坏"与"上游没有图"）。"""
    if not source.lower().startswith(('http://', 'https://')):
        return False
    code, headers = _curl(source, os.path.join(workdir, 'upstream'), timeout=25, headers=True)
    return _serves_real_cover(code, headers)


def main() -> int:
    parser = argparse.ArgumentParser(description='检查 /cover 同源代理能否收敛到真封面')
    parser.add_argument('--base', default='https://bookrank-ckml.onrender.com', help='站点地址')
    parser.add_argument('--wait', type=float, default=8.0, help='两次尝试之间的等待秒数（默认 8）')
    parser.add_argument('--attempts', type=int, default=2, help='每个封面的尝试次数（默认 2）')
    parser.add_argument('--limit', type=int, default=0, help='只检查前 N 个封面（0=全部）')
    parser.add_argument(
        '--distinguish-upstream',
        action='store_true',
        help='对卡住的封面额外直连源站，区分"代理侧坏"(RED) 与"上游本就没有图"(WARN)',
    )
    args = parser.parse_args()

    if args.attempts < 1:
        parser.error('--attempts 必须 >= 1')
    if args.attempts == 1:
        # 单次尝试无法区分"冷缓存"与"永久占位"：/cover 是 block=False 设计，
        # 部署/重启后 Render 的临时盘被清空，**所有**封面都会先 302 一次。
        # 只探一次必然把大批冷封面误报成 RED（实测踩过）。
        print('⚠️ --attempts 1：冷缓存会被误报为永久占位（/cover 首次必定 302）。只适合冒烟测试，不要用它下结论。\n')

    workdir = tempfile.mkdtemp(prefix='cover-check-')
    try:
        print(f'=== 1/2 收集封面源（{args.base}）===')
        sources = collect_cover_sources(args.base, workdir)
        if args.limit:
            sources = sources[: args.limit]
        if not sources:
            print('没有收集到任何封面源，无法判断')
            return 1

        print(f'\n=== 2/2 逐个请求 /cover（共 {len(sources)} 个，最多尝试 {args.attempts} 次，间隔 {args.wait}s）===')
        verdicts: collections.Counter[str] = collections.Counter()
        proxy_stuck: list[str] = []
        upstream_stuck: list[str] = []
        for index, source in enumerate(sources, 1):
            code, headers = probe_cover(args.base, source, workdir, args.wait, args.attempts)
            if _serves_real_cover(code, headers):
                # x-cover-source=cache 表示第一次就命中；否则说明是冷缓存后收敛的
                key = 'warm' if headers.get('x-cover-source') == 'cache' else 'cold-converged'
                verdicts[key] += 1
                if key == 'cold-converged':
                    print(f'  [{index:3d}] 冷缓存→已收敛  {source[:96]}')
                continue

            if args.distinguish_upstream and not upstream_has_image(source, workdir):
                verdicts['stuck-upstream'] += 1
                upstream_stuck.append(source)
                print(f'  [{index:3d}] 上游无图(WARN)  {source[:96]}')
                continue

            verdicts['stuck-proxy' if args.distinguish_upstream else 'stuck'] += 1
            proxy_stuck.append(source)
            print(
                f'  [{index:3d}] **永久占位**  {source[:96]}\n'
                f'          http={code} 字节={headers.get("_bytes")} '
                f'location={headers.get("location", "")[-32:]}'
            )

        print('\n=== 汇总 ===')
        print(f'  热缓存直接命中        {verdicts["warm"]}')
        print(f'  冷缓存但已收敛        {verdicts["cold-converged"]}')
        if args.distinguish_upstream:
            print(f'  上游本就没有图(WARN)  {verdicts["stuck-upstream"]}')
            print(f'  代理侧永久占位(RED)   {verdicts["stuck-proxy"]}')
        else:
            print(f'  永久停在占位图        {verdicts["stuck"]}')

        total = len(sources)
        if proxy_stuck:
            print(f'\nVERDICT: RED —— {len(proxy_stuck)}/{total} 张封面在代理侧永久不可用')
            for source in proxy_stuck[:10]:
                print('   -', source)
            http_ones = [s for s in proxy_stuck if s.startswith('http://')]
            if http_ones:
                print(
                    f'\n  其中 {len(http_ones)} 个是 http:// 形态 —— 这正是'
                    ' app/utils/cover_urls.py:normalize_cover_url 要处理的那类值'
                    '（两道门判据不一致会让它们永久停在占位图）'
                )
        elif upstream_stuck:
            print(
                f'\nVERDICT: WARN —— 代理侧无问题；{len(upstream_stuck)}/{total} 张封面'
                '上游本身就没有图（数据问题，不是代理 bug）'
            )
        else:
            print(f'\nVERDICT: GREEN —— {total} 张封面全部可收敛到真图')
        return 1 if proxy_stuck else 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
