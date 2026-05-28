"""
翻译脏数据修复脚本

修复数据库中已有的AI翻译污染数据：
- **书名：** / **作者：** / **简介：** 等前缀
- Markdown ** 标记残留
- 多字段内容粘连（如书名+作者+简介混在一起）

使用方法:
    python fix_translation_data.py [--dry-run]

--dry-run: 只预览，不实际修改数据库
"""

import logging
import re
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# 常见翻译污染标记
_DIRTY_MARKERS = (
    '书名',
    '作者',
    '简介',
    '描述',
    '详情',
    '出版社',
    'Title:',
    'Author:',
    'Description:',
    'Summary:',
    'Details:',
    'Publisher:',
    '翻译：',
    '译文：',
    '**',
    '__',
    '`',
)

# "译"后缀正则（匹配标题末尾的"译"字，如"希望升起译"）
_RE_TRANSLATE_SUFFIX = re.compile(r'[\s]*译$|[\s]*\[译\]$|[\s]*\(译\)$')


def is_dirty(text: str | None) -> bool:
    """检测文本是否包含翻译污染标记"""
    if not text:
        return False
    if any(marker in text for marker in _DIRTY_MARKERS):
        return True
    return bool(_RE_TRANSLATE_SUFFIX.search(text))


def clean_title(text: str) -> str:
    """清理书名字段（委托到统一后处理函数）"""
    from app.utils.api_helpers import clean_translation_text

    return clean_translation_text(text, field_type='title')


def clean_description(text: str) -> str:
    """清理简介/描述字段（委托到统一后处理函数）"""
    from app.utils.api_helpers import clean_translation_text

    return clean_translation_text(text, field_type='description')


def main():
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        logger.info('【预览模式】不会实际修改数据库')
    else:
        logger.info('【执行模式】将实际修改数据库')

    # 初始化Flask应用上下文
    from app import create_app

    app = create_app()

    with app.app_context():
        from app.models.database import db
        from app.models.new_book import NewBook
        from app.models.schemas import BookMetadata

        total_fixed = 0
        total_checked = 0

        # 1. 修复 BookMetadata 表
        logger.info('=' * 50)
        logger.info('开始检查 BookMetadata 表...')

        metas = BookMetadata.query.all()
        for meta in metas:
            if is_dirty(meta.title_zh):
                old = meta.title_zh
                meta.title_zh = clean_title(old)
                logger.info(f"[BookMetadata.title_zh] {meta.isbn}: '{old[:60]}...' -> '{meta.title_zh[:60]}...'")
                total_fixed += 1

            if is_dirty(meta.description_zh):
                old = meta.description_zh
                meta.description_zh = clean_description(old)
                logger.info(
                    f"[BookMetadata.description_zh] {meta.isbn}: '{old[:60]}...' -> '{meta.description_zh[:60]}...'"
                )
                total_fixed += 1

            if is_dirty(meta.details_zh):
                old = meta.details_zh
                meta.details_zh = clean_description(old)
                logger.info(f"[BookMetadata.details_zh] {meta.isbn}: '{old[:60]}...' -> '{meta.details_zh[:60]}...'")
                total_fixed += 1

            total_checked += 1

        # 2. 修复 NewBook 表
        logger.info('=' * 50)
        logger.info('开始检查 NewBook 表...')

        books = NewBook.query.all()
        for book in books:
            if is_dirty(book.title_zh):
                old = book.title_zh
                book.title_zh = clean_title(old)
                logger.info(f"[NewBook.title_zh] ID={book.id}: '{old[:60]}...' -> '{book.title_zh[:60]}...'")
                total_fixed += 1

            if is_dirty(book.description_zh):
                old = book.description_zh
                book.description_zh = clean_description(old)
                logger.info(
                    f"[NewBook.description_zh] ID={book.id}: '{old[:60]}...' -> '{book.description_zh[:60]}...'"
                )
                total_fixed += 1

            total_checked += 1

        # 提交
        if not dry_run and total_fixed > 0:
            try:
                db.session.commit()
                logger.info('数据库提交成功')
            except Exception as e:
                db.session.rollback()
                logger.error(f'数据库提交失败: {e}')
                return 1

        logger.info('=' * 50)
        logger.info(f'检查完成：共检查 {total_checked} 条记录，修复 {total_fixed} 个字段')
        if dry_run:
            logger.info('【预览模式】未实际修改数据库，去掉 --dry-run 参数执行修复')

    return 0


if __name__ == '__main__':
    sys.exit(main())
