#!/usr/bin/env python3
"""A/B 对比 GLM-4.7-Flash 与 tencent/Hunyuan-MT-7B 的图书翻译质量（离线）。

背景：bookrank 现网翻译走智谱 GLM-4.7-Flash。本脚本评估"是否改用硅基流动的
Hunyuan-MT-7B"。为保证公平，两个模型使用与生产【完全相同】的字段 prompt
（从 app/services/zhipu_translation_service.py 的 _field_prompts 通过 AST 提取，
不触发 app 包导入；失败时降级到内置副本）与相同的调用参数。

产出（写入 --out-dir，默认 scripts/ab_output/）：
  ab_report.json          原始结果（耗时 / token / 污染标记 / 失败原因）
  ab_scoring.csv          人工双盲评分表（A/B 顺序可随机化；映射在 ab_blinding_key.json）
  ab_summary.txt          控制台摘要（同名内容同时打印）

用法：
  set ZHIPU_API_KEY=xxx          # 智谱 key（GLM-4.7-Flash）
  set SILICONFLOW_API_KEY=xxx    # 硅基流动 key（Hunyuan-MT-7B；缺省则只跑 GLM）
  python scripts/ab_compare_translation_models.py --samples scripts/ab_translation_samples.json --blinded
  python scripts/ab_compare_translation_models.py --check-merged   # 额外演示"合并 JSON 调用"在 Hunyuan 上是否可行

依赖：zhipuai（仓库已有）、openai（如缺会提示安装，仅 Hunyuan 侧需要）。
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICE_PATH = REPO_ROOT / 'app' / 'services' / 'zhipu_translation_service.py'
HELPERS_PATH = REPO_ROOT / 'app' / 'utils' / 'api_helpers.py'
DEFAULT_SAMPLES = REPO_ROOT / 'scripts' / 'ab_translation_samples.json'
DEFAULT_OUT_DIR = REPO_ROOT / 'scripts' / 'ab_output'

GLM_MODEL = 'glm-4.7-flash'
HUNYUAN_MODEL = 'tencent/Hunyuan-MT-7B'
SILICONFLOW_BASE_URL = 'https://api.siliconflow.cn/v1'
TEMPERATURE = 0.3  # 与生产 translate() / translate_book_fields() 一致
MAX_TOKENS = 4096

# 生产 translate_book_fields() 的合并 JSON prompt（诊断用，与源码保持同步）
MERGED_JSON_PROMPT = (
    '你是一位资深图书翻译专家，请将以下英文图书信息翻译为中文。\n'
    '请严格按JSON格式输出，包含以下键：\n'
    '- "title_zh": 书名翻译（纯文字，不加书名号《》）\n'
    '- "description_zh": 简介翻译\n'
    '- "details_zh": 详情翻译\n'
    '规则：\n'
    '- 书名：文学性意译/专业直译，不加《》和后缀\n'
    '- 简介：流畅自然，专有名词附原文，书中书名用《》\n'
    '- 详情：出版信息准确，出版社附英文原名，ISBN不翻译\n'
    '- 只输出JSON，不添加任何其他文字、注释或Markdown标记'
)

# AST 提取失败时的降级 prompt（尽量贴近生产；正常情况不会用到）
_FALLBACK_PROMPTS = {
    'title': (
        '你是一位资深图书翻译专家，正在翻译英文书名为中文。\n'
        '规则：文学性书名采用意译，体现文学美感；专业/技术书籍采用直译，保持准确性；'
        '不添加书名号《》，只输出纯文字书名；禁止输出任何前缀、注释、英文原文或"译"后缀。\n'
        '示例："The Great Gatsby" → 了不起的盖茨比\n"Dune" → 沙丘'
    ),
    'description': (
        '你是一位资深图书翻译专家，正在翻译英文图书简介为中文。\n'
        '规则：准确传达原意，不添加原文没有的内容；流畅自然，符合中文阅读习惯；'
        '专有名词首次出现时附英文原文；书中书名用《》；只输出翻译结果，不加任何标签或Markdown。'
    ),
    'text': (
        '你是一位资深翻译专家，将英文翻译为中文。\n'
        '规则：准确传达原意，符合中文表达习惯，避免翻译腔；只输出翻译结果，不加任何前缀或注释。'
    ),
}


# --------------------------------------------------------------------------
# 从源码安全提取生产常量（不 import app 包，避免拉起 Flask/DB）
# --------------------------------------------------------------------------
def _extract_assign_from_source(path: Path, name: str):
    """读取 Python 源码，返回任意位置 `name = <字面量>` 或 `self.name = <字面量>` 的值。

    - `_DIRTY_MARKERS` 是顶层 `Name` 目标（`Assign` 节点）；
    - `_field_prompts` 是 `__init__` 里的 `self._field_prompts: dict[str, str] = {...}`
      （带类型注解，AST 节点是 `AnnAssign` 而非 `Assign`）。
    用 ast.literal_eval：字符串隐式拼接在解析阶段已合并为单个字面量，可直接求值。
    """
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except (OSError, SyntaxError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue
        for target in targets:
            hit = (isinstance(target, ast.Name) and target.id == name) or (
                isinstance(target, ast.Attribute) and target.attr == name
            )
            if hit:
                try:
                    return ast.literal_eval(value)
                except (ValueError, TypeError, SyntaxError):
                    return None
    return None


def load_prompts() -> dict[str, str]:
    prompts = _extract_assign_from_source(SERVICE_PATH, '_field_prompts')
    if not prompts:
        print('[warn] 未能从源码提取 _field_prompts，使用内置降级 prompt', file=sys.stderr)
        return _FALLBACK_PROMPTS
    return prompts


def load_dirty_markers() -> tuple[str, ...]:
    markers = _extract_assign_from_source(HELPERS_PATH, '_DIRTY_MARKERS')
    if not markers:
        return ()
    return tuple(markers)


# --------------------------------------------------------------------------
# 数据加载
# --------------------------------------------------------------------------
def load_samples(path: Path, limit: int | None) -> list[dict]:
    samples = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(samples, list) or not samples:
        raise SystemExit(f'样本文件格式错误或为空: {path}')
    if limit:
        samples = samples[:limit]
    return samples


# --------------------------------------------------------------------------
# Provider 客户端（懒加载，缺 key 自动跳过）
# --------------------------------------------------------------------------
def build_clients() -> dict[str, object]:
    clients: dict[str, object] = {}
    zhipu_key = os.environ.get('ZHIPU_API_KEY', '').strip()
    if zhipu_key:
        try:
            from zhipuai import ZhipuAI

            clients['glm'] = ZhipuAI(api_key=zhipu_key, timeout=60.0)
        except ImportError:
            print('[warn] 未安装 zhipuai，跳过 GLM 侧: pip install zhipuai', file=sys.stderr)
    else:
        print('[warn] 未设置 ZHIPU_API_KEY，跳过 GLM 侧', file=sys.stderr)

    sf_key = os.environ.get('SILICONFLOW_API_KEY', '').strip()
    if sf_key:
        try:
            from openai import OpenAI

            clients['hunyuan'] = OpenAI(api_key=sf_key, base_url=SILICONFLOW_BASE_URL)
        except ImportError:
            print('[warn] 未安装 openai，跳过 Hunyuan 侧: pip install openai', file=sys.stderr)
    else:
        print('[warn] 未设置 SILICONFLOW_API_KEY，跳过 Hunyuan 侧', file=sys.stderr)

    if not clients:
        raise SystemExit('至少需要 ZHIPU_API_KEY 或 SILICONFLOW_API_KEY 之一。')
    return clients


def call_chat(client: object, model: str, prompt: str, text: str) -> dict:
    """单次 chat.completions 调用（与生产参数一致），返回结果/指标。"""
    start = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': text},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        content = (resp.choices[0].message.content or '').strip()
        usage = getattr(resp, 'usage', None)
        return {
            'ok': True,
            'content': content,
            'latency_ms': latency_ms,
            'prompt_tokens': getattr(usage, 'prompt_tokens', None),
            'completion_tokens': getattr(usage, 'completion_tokens', None),
            'error': None,
        }
    except Exception as e:  # noqa: BLE001 - 统一收集 provider 错误，不中断整批
        return {
            'ok': False,
            'content': None,
            'latency_ms': round((time.perf_counter() - start) * 1000, 1),
            'prompt_tokens': None,
            'completion_tokens': None,
            'error': f'{type(e).__name__}: {e}',
        }


def is_polluted(text: str, markers: tuple[str, ...]) -> bool:
    """命中生产 _DIRTY_MARKERS（书名：/Title:/**/`` 等）即视为污染。"""
    return bool(markers) and any(m in text for m in markers)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run_sample(
    sample: dict,
    clients: dict[str, object],
    prompts: dict[str, str],
    markers: tuple[str, ...],
    check_merged: bool,
) -> dict:
    title_en = (sample.get('title') or '').strip()
    desc_en = (sample.get('description') or '').strip()
    result: dict = {'id': sample['id'], 'title_en': title_en, 'description_en': desc_en, 'models': {}}

    for provider, client in clients.items():
        entry: dict = {}
        if title_en:
            entry['title'] = call_chat(client, GLM_MODEL if provider == 'glm' else HUNYUAN_MODEL,
                                       prompts.get('title', prompts['text']), title_en)
        if desc_en:
            entry['description'] = call_chat(client, GLM_MODEL if provider == 'glm' else HUNYUAN_MODEL,
                                             prompts.get('description', prompts['text']), desc_en)
        if check_merged and title_en and desc_en:
            merged_text = f'Title: {title_en}\nDescription: {desc_en}'
            call = call_chat(client, GLM_MODEL if provider == 'glm' else HUNYUAN_MODEL,
                             MERGED_JSON_PROMPT, merged_text)
            parsed_ok = False
            if call['ok'] and call['content']:
                txt = call['content']
                # 与生产一致：先剥 markdown 围栏，再整段 json.loads，再尝试夹取 {} 兜底
                if txt.startswith('```'):
                    txt = txt.split('```', 2)[1] if txt.count('```') >= 2 else txt
                try:
                    json.loads(txt)
                    parsed_ok = True
                except json.JSONDecodeError:
                    brace_start, brace_end = txt.find('{'), txt.rfind('}')
                    if brace_start != -1 and brace_end > brace_start:
                        try:
                            json.loads(txt[brace_start : brace_end + 1])
                            parsed_ok = True
                        except json.JSONDecodeError:
                            parsed_ok = False
            entry['merged_json'] = {'ok': parsed_ok, 'raw_head': (call['content'] or '')[:80]}
        result['models'][provider] = entry
    return result


def build_scoring_rows(report: list[dict], blinded: bool) -> tuple[list[dict], dict]:
    """生成人工评分行；blinded 时每样本随机 A/B 归属，映射写回 key。"""
    rows, key = [], {}
    providers = [p for p in ('glm', 'hunyuan') if any(p in s['models'] for s in report)]
    for s in report:
        order = providers[:]
        if blinded and len(order) == 2:
            random.shuffle(order)
        key[s['id']] = {'A': order[0], 'B': order[1]} if len(order) == 2 else {'A': order[0], 'B': None}
        row = {
            'sample_id': s['id'],
            'title_en': s['title_en'],
            'description_en': s['description_en'],
        }
        for label, provider in (('A', order[0]), ('B', order[1] if len(order) == 2 else None)):
            if provider is None:
                continue
            entry = s['models'].get(provider, {})
            row[f'模型{label}_书名'] = _content_of(entry.get('title')) or '(失败)'
            row[f'模型{label}_简介'] = _content_of(entry.get('description')) or '(失败)'
        # 空评分列
        for label in ('A', 'B'):
            for dim in ('忠实度', '流畅度', '吸引力'):
                row[f'模型{label}_{dim}(1-5)'] = ''
        row['备注'] = ''
        rows.append(row)
    return rows, key


def _content_of(call: dict | None) -> str | None:
    if not call:
        return None
    return call.get('content') if call.get('ok') else None


def write_outputs(
    report: list[dict],
    rows: list[dict],
    key: dict,
    out_dir: Path,
    blinded: bool,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'ab_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    with (out_dir / 'ab_scoring.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    if blinded:
        (out_dir / 'ab_blinding_key.json').write_text(
            json.dumps(key, ensure_ascii=False, indent=2), encoding='utf-8'
        )


def print_summary(report: list[dict], clients: dict[str, object], markers: tuple[str, ...]) -> str:
    lines = ['=' * 72, 'A/B 摘要: GLM-4.7-Flash vs tencent/Hunyuan-MT-7B', '=' * 72]
    agg = {p: {'ok': 0, 'fail': 0, 'polluted': 0, 'lat_ms': [], 'tok': []} for p in clients}
    for s in report:
        for provider, entry in s['models'].items():
            a = agg[provider]
            for field in ('title', 'description'):
                call = entry.get(field)
                if not call:
                    continue
                if call['ok']:
                    a['ok'] += 1
                    a['lat_ms'].append(call['latency_ms'])
                    if call['completion_tokens']:
                        a['tok'].append(call['completion_tokens'])
                    if is_polluted(call['content'], markers):
                        a['polluted'] += 1
                else:
                    a['fail'] += 1
            mj = entry.get('merged_json')
            if mj is not None:
                lines.append(f"[merged-json] {provider}: 可解析={mj['ok']}  原文头: {mj['raw_head']!r}")
    for provider, a in agg.items():
        avg_lat = (sum(a['lat_ms']) / len(a['lat_ms'])) if a['lat_ms'] else 0.0
        avg_tok = (sum(a['tok']) / len(a['tok'])) if a['tok'] else 0.0
        lines.append(
            f'{provider:8s} 成功={a["ok"]:3d} 失败={a["fail"]:3d} 污染={a["polluted"]:3d} '
            f'平均耗时={avg_lat:7.1f}ms 平均输出tok={avg_tok:6.1f}'
        )
    lines.append('=' * 72)
    text = '\n'.join(lines)
    print(text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description='GLM-4.7-Flash vs Hunyuan-MT-7B 图书翻译 A/B 对比')
    parser.add_argument('--samples', type=Path, default=DEFAULT_SAMPLES, help='样本 JSON 路径')
    parser.add_argument('--limit', type=int, default=None, help='只跑前 N 条样本')
    parser.add_argument('--out-dir', type=Path, default=DEFAULT_OUT_DIR, help='输出目录')
    parser.add_argument('--blinded', action='store_true', help='评分表 A/B 随机化（映射存 ab_blinding_key.json）')
    parser.add_argument('--check-merged', action='store_true', help='额外演示合并 JSON 调用能否解析')
    args = parser.parse_args()

    if not args.samples.exists():
        raise SystemExit(f'样本文件不存在: {args.samples}')
    samples = load_samples(args.samples, args.limit)
    prompts = load_prompts()
    markers = load_dirty_markers()
    clients = build_clients()
    print(f'[info] 样本 {len(samples)} 条, provider: {", ".join(clients)}')

    report = [
        run_sample(s, clients, prompts, markers, args.check_merged)
        for s in samples
    ]
    rows, key = build_scoring_rows(report, args.blinded)
    write_outputs(report, rows, key, args.out_dir, args.blinded)
    text = print_summary(report, clients, markers)

    with (args.out_dir / 'ab_summary.txt').open('w', encoding='utf-8') as f:
        f.write(text)
    print(f'[info] 结果已写入: {args.out_dir}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
