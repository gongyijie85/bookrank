"""封面可用性自检：判断"国内不挂 VPN 的用户能不能看到真封面"。

## 为什么需要这个脚本

`/cover` 是**同源代理**（见 app/routes/main.py:cover_proxy）：浏览器只请求本站，
由服务端回源到境外图床并落盘缓存。所以判断封面是否可用，不能只看 SSR HTML
（那里永远是 `/cover?src=…`，看不出对错），必须**真的请求一次 `/cover`** 看它回的是
图片字节还是占位图。

设计上 `/cover` 是 `block=False`：缓存 MISS 时立刻 302 到 `default-cover.png`
（并带 `no-store`），由后台线程回源落盘，靠前端 `static/js/cover.js` 按
0.8/2/5/12s 重试等到真图。因此"第一次 302、过几秒再请求 200"是**正常**的；
"反复请求一直 302"才是坏 —— 那说明后台预取从未成功，用户看到的是永久占位图。

已知会落入这个坑的一类值：`http://` 开头的封面源。图片缓存下载守卫
（app/services/api_utils.py:_is_safe_image_url）只允许 https，
而 Google Books API 的 `imageLinks.thumbnail` 默认返回
`http://books.google.com/…&source=gbs_api`。守卫的拒绝发生在提交后台预取**之前**，
于是这类封面永远只是占位图 —— 修复见 app/utils/cover_urls.py:normalize_cover_url。

## 用法

    python scripts/check_cover_proxy.py                     # 自检生产
    python scripts/check_cover_proxy.py --base http://127.0.0.1:5000
    python scripts/check_cover_proxy.py --wait 10 --limit 20

退出码：0 = 全部封面可收敛；1 = 存在永久卡住的封面（RED）。

## ⚠️ 运行环境要先自证

本脚本跑在**你的机器**上，只请求本站 `/cover`，所以结果与你的网络所在地无关 ——
这正是要点（浏览器同样只请求本站）。但如果你想顺便确认"境外图床是否被我这边
直连"，加 `--probe-upstream`：它会直连一次源站。注意**公司/运营商级代理会让直连
测试失真**（curl 会打出 `HTTP/1.1 200 Connection Established`），所以那个结果
只作参考，不能作为"国内可达"的证据。
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys
import time
import urllib.parse

PAGES: tuple[str, ...] = ('/', '/new-books', '/awards')
DESKTOP_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)
COVER_SRC_RE = re.compile(r'/cover\?src=([^"\'\s>]+)')
DEFAULT_COVER = '/static/default-cover.png'


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


def collect_cover_sources(base: str, tmp_prefix: str) -> list[str]:
    """从若干列表页收集去重后的封面源地址。"""
    ordered: list[str] = []
    seen: set[str] = set()
    for page in PAGES:
        code, _ = _curl(base + page, tmp_prefix + '.page')
        if code != 200:
            print(f'  ! {page} 返回 {code}，跳过')
            continue
        with open(tmp_prefix + '.page', encoding='utf-8', errors='replace') as fh:
            html = fh.read()
        for raw in COVER_SRC_RE.findall(html):
            source = urllib.parse.unquote(raw)
            if source not in seen:
                seen.add(source)
                ordered.append(source)
        print(f'  {page}: 累计 {len(ordered)} 个不同封面源')
    return ordered


def probe_upstream(sources: list[str]) -> None:
    """参考信息：直连源站是否可达。代理会污染结论，只作提示。"""
    hosts = sorted({urllib.parse.urlsplit(s).netloc for s in sources})
    print('\n=== 附：源站直连可达性（仅供参考，代理会让它失真）===')
    for host in hosts:
        code, info = _curl(f'https://{host}/', '.debug/_cover_upstream.bin', timeout=15, headers=True)
        print(f'  {code:>4} {host}  bytes={info.get("_bytes")}')


def main() -> int:
    parser = argparse.ArgumentParser(description='检查 /cover 同源代理能否收敛到真封面')
    parser.add_argument('--base', default='https://bookrank-ckml.onrender.com', help='站点地址')
    parser.add_argument('--wait', type=float, default=8.0, help='冷缓存复探前等待秒数（默认 8）')
    parser.add_argument('--limit', type=int, default=0, help='只检查前 N 个封面（0=全部）')
    parser.add_argument('--probe-upstream', action='store_true', help='额外测一次源站直连')
    args = parser.parse_args()

    tmp = '.debug/_cover_check'
    os.makedirs('.debug', exist_ok=True)

    print(f'=== 1/2 收集封面源（{args.base}）===')
    sources = collect_cover_sources(args.base, tmp)
    if args.limit:
        sources = sources[: args.limit]
    if not sources:
        print('没有收集到任何封面源，无法判断')
        return 1

    print(f'\n=== 2/2 逐个请求 /cover（共 {len(sources)} 个，间隔 {args.wait}s 复探）===')
    verdicts: collections.Counter[str] = collections.Counter()
    stuck: list[str] = []
    for index, source in enumerate(sources, 1):
        url = args.base + '/cover?' + urllib.parse.urlencode({'src': source})
        first, first_headers = _curl(url, tmp + '.b1', headers=True)
        if first == 200 and first_headers.get('x-cover-source') == 'cache':
            verdicts['warm'] += 1
            continue
        time.sleep(args.wait)
        second, second_headers = _curl(url, tmp + '.b2', headers=True)
        if second == 200 and second_headers.get('x-cover-source') == 'cache':
            verdicts['cold-converged'] += 1
            print(f'  [{index:3d}] 冷缓存→已收敛  {source[:96]}')
        else:
            verdicts['stuck'] += 1
            stuck.append(source)
            print(
                f'  [{index:3d}] **永久占位**  {source[:96]}\n'
                f'          首次={first} 复探={second} '
                f'字节={first_headers.get("_bytes")}/{second_headers.get("_bytes")} '
                f'location={first_headers.get("location", "")[-32:]}'
            )

    print('\n=== 汇总 ===')
    print(f'  热缓存直接命中        {verdicts["warm"]}')
    print(f'  冷缓存但已收敛        {verdicts["cold-converged"]}')
    print(f'  永久停在占位图        {verdicts["stuck"]}')
    total = len(sources)
    if verdicts['stuck']:
        print(f'\nVERDICT: RED —— {verdicts["stuck"]}/{total} 张封面对任何用户都不可用')
        for source in stuck[:10]:
            print('   -', source)
        hint = [s for s in stuck if s.startswith('http://')]
        if hint:
            print(
                f'\n  其中 {len(hint)} 个是 http:// 形态 —— 这正是'
                ' app/utils/cover_urls.py:normalize_cover_url 要修的那类值'
            )
    else:
        print(f'\nVERDICT: GREEN —— {total} 张封面全部可收敛到真图')
    if args.probe_upstream:
        probe_upstream(sources)
    return 1 if verdicts['stuck'] else 0


if __name__ == '__main__':
    sys.exit(main())
