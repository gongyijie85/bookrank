#!/usr/bin/env python3
"""
清理翻译数据中残留的"译"字后缀

修复 GLM 模型翻译书名时偶尔在末尾添加"译"字的问题。
遍历 book_metadata 和 translation_cache 表，清理脏数据。

用法：
    python scripts/fix_translation_suffix.py          # 直接执行清理
    python scripts/fix_translation_suffix.py --dry-run # 仅预览变更
"""

import argparse
import os
import re
import sys

# 将项目根目录加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def clean_yi_suffix(text: str) -> str | None:
    """
    清除文本末尾的"译"字后缀及其变体

    处理以下变体：
    - "希望升起译" → "希望升起"
    - "希望升起 译" → "希望升起"
    - "希望升起[译]" → "希望升起"
    - "希望升起(译)" → "希望升起"
    - "希望升起译\n简介..." → "希望升起\n简介..."
    - "译希望升起" → "希望升起"（行首兜底）
    """
    if not text:
        return None

    original = text
    # 处理行尾各种变体：译、[译]、(译)、空格+译
    text = re.sub(r'[\s]*译$', '', text)
    text = re.sub(r'[\s]*\[译\]$', '', text)
    text = re.sub(r'[\s]*\(译\)$', '', text)
    # 处理换行前的"译"字
    text = re.sub(r'[\s]*译[\s]*\n', '\n', text)
    # 处理行首的"译"字（兜底）
    text = re.sub(r'^[\s]*译[\s]*', '', text)

    # 如果清理后内容有变化，返回清理后的内容
    if text != original:
        return text.strip()
    return None


def fix_book_metadata(dry_run: bool = False) -> int:
    """
    修复 book_metadata 表中的脏翻译数据

    Args:
        dry_run: 是否为预览模式（不实际写入数据库）

    Returns:
        修复的记录数
    """
    from app.models.database import db
    from app.models.schemas import BookMetadata

    fixed_count = 0

    # 查询所有包含"译"字的中文翻译字段
    records = BookMetadata.query.filter(
        db.or_(
            BookMetadata.title_zh.like('%译'),
            BookMetadata.title_zh.like('%译]%'),
            BookMetadata.title_zh.like('%(译)%'),
            BookMetadata.description_zh.like('%译'),
            BookMetadata.description_zh.like('%译]%'),
            BookMetadata.description_zh.like('%(译)%'),
            BookMetadata.details_zh.like('%译'),
            BookMetadata.details_zh.like('%译]%'),
            BookMetadata.details_zh.like('%(译)%'),
        )
    ).all()

    print(f"[book_metadata] 发现 {len(records)} 条可能包含'译'字标记的记录")

    for record in records:
        changed = False

        for field in ['title_zh', 'description_zh', 'details_zh']:
            value = getattr(record, field)
            if value:
                cleaned = clean_yi_suffix(value)
                if cleaned is not None:
                    print(f"  修复 [{record.isbn}] {field}: '{value}' → '{cleaned}'")
                    if not dry_run:
                        setattr(record, field, cleaned)
                    changed = True

        if changed:
            fixed_count += 1

    if not dry_run and fixed_count > 0:
        db.session.commit()
        print(f'[book_metadata] 已修复 {fixed_count} 条记录')
    else:
        print(f'[book_metadata] {"预览模式" if dry_run else "实际修复"}: {fixed_count} 条记录需要修复')

    return fixed_count


def fix_translation_cache(dry_run: bool = False) -> int:
    """
    修复 translation_cache 表中的脏翻译数据

    Args:
        dry_run: 是否为预览模式

    Returns:
        修复的记录数
    """
    from app.models.database import db
    from app.models.schemas import TranslationCache

    fixed_count = 0

    # 查询所有翻译结果包含"译"字的缓存记录
    records = TranslationCache.query.filter(
        db.or_(
            TranslationCache.translated_text.like('%译'),
            TranslationCache.translated_text.like('%译]%'),
            TranslationCache.translated_text.like('%(译)%'),
        )
    ).all()

    print(f"[translation_cache] 发现 {len(records)} 条可能包含'译'字标记的缓存记录")

    for record in records:
        original = record.translated_text
        cleaned = clean_yi_suffix(original)
        if cleaned is not None:
            print(
                f"  修复 [{record.id}] source_hash={record.source_hash[:16]}...: '{original[:60]}...' → '{cleaned[:60]}...'"
            )
            if not dry_run:
                record.translated_text = cleaned
            fixed_count += 1

    if not dry_run and fixed_count > 0:
        db.session.commit()
        print(f'[translation_cache] 已修复 {fixed_count} 条缓存记录')
    else:
        print(f'[translation_cache] {"预览模式" if dry_run else "实际修复"}: {fixed_count} 条记录需要修复')

    return fixed_count


def fix_static_json_files(dry_run: bool = False) -> int:
    """
    修复 static/data 目录下 JSON 缓存文件中的脏数据

    Args:
        dry_run: 是否为预览模式

    Returns:
        修复的文件数
    """
    import json
    from pathlib import Path

    data_dir = Path(__file__).parent.parent / 'static' / 'data'
    if not data_dir.exists():
        print('[static_json] 数据目录不存在，跳过')
        return 0

    fixed_files = 0
    json_files = list(data_dir.glob('*.json'))

    for json_file in json_files:
        try:
            with open(json_file, encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        changed = False

        # 处理列表格式的 JSON（如 all_books.json）
        _jf_name = json_file.name
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    for field in ['title_zh', 'description_zh', 'details_zh', 'author_zh']:
                        value = item.get(field)
                        if isinstance(value, str):
                            cleaned = clean_yi_suffix(value)
                            if cleaned is not None:
                                print(f"  修复 [{_jf_name}] {field}: '{value}' → '{cleaned}'")
                                item[field] = cleaned
                                changed = True

        # 处理字典格式的 JSON（如 update_time.json）
        elif isinstance(data, dict):
            # 递归处理嵌套结构
            def fix_dict(obj, _jf=json_file):
                nonlocal changed
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if key in ['title_zh', 'description_zh', 'details_zh', 'author_zh'] and isinstance(value, str):
                            cleaned = clean_yi_suffix(value)
                            if cleaned is not None:
                                print(f"  修复 [{_jf.name}] {key}: '{value}' → '{cleaned}'")
                                obj[key] = cleaned
                                changed = True
                        elif isinstance(value, (dict, list)):
                            fix_dict(value)
                elif isinstance(obj, list):
                    for item in obj:
                        fix_dict(item)

            fix_dict(data)

        if changed:
            fixed_files += 1
            if not dry_run:
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f'[static_json] 已更新文件: {json_file.name}')
            else:
                print(f'[static_json] [预览] 需要更新文件: {json_file.name}')

    print(f'[static_json] {"预览模式" if dry_run else "实际修复"}: {fixed_files} 个文件需要修复')
    return fixed_files


def main():
    parser = argparse.ArgumentParser(description='清理翻译数据中残留的"译"字后缀')
    parser.add_argument('--dry-run', action='store_true', help='预览模式，不实际写入数据库')
    args = parser.parse_args()

    print(f'{"=" * 60}')
    print('翻译脏数据清理工具')
    print(f'模式: {"预览 (dry-run)" if args.dry_run else "实际执行"}')
    print(f'{"=" * 60}\n')

    # 创建 Flask 应用上下文
    from app import create_app

    app = create_app()

    with app.app_context():
        total_fixed = 0

        # 1. 修复 book_metadata 表
        total_fixed += fix_book_metadata(dry_run=args.dry_run)

        # 2. 修复 translation_cache 表
        total_fixed += fix_translation_cache(dry_run=args.dry_run)

        # 3. 修复静态 JSON 文件
        total_fixed += fix_static_json_files(dry_run=args.dry_run)

        print(f'\n{"=" * 60}')
        if args.dry_run:
            print(f'预览完成，共发现 {total_fixed} 处需要修复')
            print('如需实际执行，请去掉 --dry-run 参数重新运行')
        else:
            print(f'清理完成，共修复 {total_fixed} 处脏数据')
        print(f'{"=" * 60}')


if __name__ == '__main__':
    main()
