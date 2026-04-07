#!/usr/bin/env python3
"""
综合数据同步脚本 - Wikidata + Open Library API

通过 Wikidata SPARQL API 获取获奖图书列表，
再通过 Open Library API 获取图书详情和封面。

用法:
    python scripts/sync_award_books_from_api.py
    python scripts/sync_award_books_from_api.py --award nebula --year 2022-2025
"""

import os
import sys
import time
import logging
import argparse
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import create_app
from app.models import db
from app.models.schemas import Award, AwardBook
from app.services import WikidataClient, OpenLibraryClient, ImageCacheService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# 奖项名称映射
AWARD_NAME_MAP = {
    'nebula': '星云奖',
    'hugo': '雨果奖',
    'booker': '布克奖',
    'international_booker': '国际布克奖',
    'pulitzer_fiction': '普利策奖',
    'edgar': '爱伦·坡奖',
    'nobel_literature': '诺贝尔文学奖',
}

# 奖项类别映射
AWARD_CATEGORY_MAP = {
    'nebula': '最佳长篇小说',
    'hugo': '最佳长篇小说',
    'booker': '小说',
    'international_booker': '翻译小说',
    'pulitzer_fiction': '小说',
    'edgar': '最佳小说',
    'nobel_literature': '文学',
}


def sync_award_books_from_api(award_keys=None, start_year=2020, end_year=2025):
    """
    从 API 同步获奖图书数据
    
    Args:
        award_keys: 奖项键名列表，None 表示所有奖项
        start_year: 开始年份
        end_year: 结束年份
    """
    app = create_app('production')
    
    with app.app_context():
        # 创建客户端
        wikidata_client = WikidataClient(timeout=30)
        openlib_client = OpenLibraryClient(timeout=10)
        image_cache = ImageCacheService(
            cache_dir=app.config['IMAGE_CACHE_DIR'],
            default_cover='/static/default-cover.png'
        )
        
        # 获取要同步的奖项
        if award_keys is None:
            award_keys = ['nebula', 'international_booker', 'edgar']
        
        logger.info(f"🚀 开始同步 {len(award_keys)} 个奖项的图书数据 ({start_year}-{end_year})...")
        
        # 从 Wikidata 获取获奖图书
        award_books = wikidata_client.get_all_award_books(
            awards=award_keys,
            start_year=start_year,
            end_year=end_year
        )
        
        total_books = sum(len(books) for books in award_books.values())
        logger.info(f"📚 从 Wikidata 获取到 {total_books} 本图书")
        
        # 处理每个奖项的图书
        for award_key, books in award_books.items():
            if not books:
                continue
            
            award_name = AWARD_NAME_MAP.get(award_key, award_key)
            category = AWARD_CATEGORY_MAP.get(award_key, '其他')
            
            logger.info(f"\n{'='*60}")
            logger.info(f"🏆 处理奖项: {award_name} ({len(books)} 本)")
            logger.info(f"{'='*60}")
            
            # 获取或创建奖项记录
            award = Award.query.filter_by(name=award_name).first()
            if not award:
                award = Award(
                    name=award_name,
                    description=f'{award_name}获奖图书',
                    country='国际' if '国际' in award_name else '美国',
                    category=category
                )
                db.session.add(award)
                db.session.flush()
                logger.info(f"✅ 创建奖项: {award_name}")
            
            # 处理每本图书
            for i, book_data in enumerate(books, 1):
                try:
                    logger.info(f"\n[{i}/{len(books)}] {book_data['title']}")
                    
                    # 获取 ISBN（优先使用 ISBN-13）
                    isbn = book_data.get('isbn13') or book_data.get('isbn10')
                    if not isbn:
                        logger.warning(f"  ⚠️ 无 ISBN，跳过")
                        continue
                    
                    # 检查是否已存在
                    existing = AwardBook.query.filter_by(
                        award_id=award.id,
                        isbn13=isbn
                    ).first()
                    
                    if existing:
                        logger.info(f"  ⏭️ 已存在，跳过")
                        continue
                    
                    # 通过 Open Library API 获取详情
                    logger.info(f"  🔍 查询 Open Library...")
                    book_details = openlib_client.fetch_book_by_isbn(isbn)
                    
                    # 获取封面 URL
                    cover_url = None
                    if book_details and book_details.get('cover_url'):
                        cover_url = book_details['cover_url']
                    else:
                        # 尝试从 Open Library Covers 获取
                        cover_url = openlib_client.get_cover_url(isbn, size='L')
                    
                    # 下载封面
                    cover_local_path = None
                    if cover_url:
                        logger.info(f"  📷 下载封面...")
                        cover_local_path = image_cache.get_cached_image_url(
                            cover_url, ttl=86400*365
                        )
                        if cover_local_path == '/static/default-cover.png':
                            cover_local_path = None
                    
                    # 创建图书记录
                    book = AwardBook(
                        award_id=award.id,
                        year=book_data['year'],
                        category=category,
                        rank=1,  # 默认排名1
                        title=book_data['title'],
                        author=book_data.get('author') or book_details.get('author') or 'Unknown',
                        description=book_details.get('description') or f'{award_name}获奖作品',
                        isbn13=isbn if len(isbn) == 13 else None,
                        isbn10=isbn if len(isbn) == 10 else None,
                        cover_original_url=cover_url,
                        cover_local_path=cover_local_path
                    )
                    
                    db.session.add(book)
                    logger.info(f"  ✅ 添加图书: {book.title[:50]}...")
                    
                    # 每3本保存一次
                    if i % 3 == 0:
                        db.session.commit()
                        logger.info(f"💾 已保存进度 ({i}/{len(books)})")
                    
                    # 延迟避免请求过快
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"  ❌ 处理失败: {e}")
                    continue
            
            # 保存当前奖项的数据
            db.session.commit()
            logger.info(f"✅ {award_name} 处理完成")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🎉 所有奖项同步完成!")
        logger.info(f"{'='*60}")


def verify_isbns(award_key=None):
    """验证数据库中图书的 ISBN 是否有效"""
    app = create_app('production')
    
    with app.app_context():
        openlib_client = OpenLibraryClient(timeout=10)
        
        query = AwardBook.query
        if award_key:
            award_name = AWARD_NAME_MAP.get(award_key, award_key)
            award = Award.query.filter_by(name=award_name).first()
            if award:
                query = query.filter_by(award_id=award.id)
        
        books = query.all()
        logger.info(f"🔍 开始验证 {len(books)} 本图书的 ISBN...")
        
        valid_count = 0
        invalid_count = 0
        
        for i, book in enumerate(books, 1):
            if not book.isbn13:
                logger.warning(f"[{i}/{len(books)}] ⚠️ {book.title}: 无 ISBN")
                invalid_count += 1
                continue
            
            try:
                book_data = openlib_client.fetch_book_by_isbn(book.isbn13)
                
                if book_data and book_data.get('title'):
                    logger.info(f"[{i}/{len(books)}] ✅ {book.title[:40]}: ISBN 有效")
                    valid_count += 1
                else:
                    logger.warning(f"[{i}/{len(books)}] ❌ {book.title[:40]}: ISBN 无效")
                    invalid_count += 1
                
                time.sleep(0.3)
                
            except Exception as e:
                logger.error(f"[{i}/{len(books)}] ❌ {book.title[:40]}: 验证失败 - {e}")
                invalid_count += 1
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ 验证完成: 有效 {valid_count} 本, 无效 {invalid_count} 本")
        logger.info(f"{'='*60}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='从 Wikidata + Open Library API 同步获奖图书数据'
    )
    parser.add_argument(
        '--award',
        nargs='+',
        choices=['nebula', 'hugo', 'booker', 'international_booker', 
                 'pulitzer_fiction', 'edgar', 'nobel_literature'],
        help='指定要同步的奖项（默认: nebula, international_booker, edgar）'
    )
    parser.add_argument(
        '--year',
        type=str,
        default='2020-2025',
        help='年份范围，格式: 开始-结束（默认: 2020-2025）'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='仅验证 ISBN，不更新数据'
    )
    
    args = parser.parse_args()
    
    if args.verify:
        verify_isbns(args.award[0] if args.award else None)
    else:
        # 解析年份范围
        year_range = args.year.split('-')
        start_year = int(year_range[0])
        end_year = int(year_range[1]) if len(year_range) > 1 else start_year
        
        sync_award_books_from_api(
            award_keys=args.award,
            start_year=start_year,
            end_year=end_year
        )
