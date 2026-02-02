#!/usr/bin/env python3
"""
补充奖项图书数据脚本

使用 Google Books API 为现有图书补充：
- 缺失的封面图片
- 详细描述
- 购买链接

使用方法:
    python scripts/enrich_award_books.py
"""

import sys
import json
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import create_app
from app.models import db
from app.models.schemas import AwardBook
from app.services.api_client import GoogleBooksClient, ImageCacheService


def enrich_award_books(batch_size: int = 20):
    """
    补充奖项图书数据
    
    Args:
        batch_size: 每批处理数量
    """
    app = create_app()
    
    with app.app_context():
        google_books = GoogleBooksClient(timeout=15)
        image_cache = ImageCacheService(
            cache_dir=app.config['IMAGE_CACHE_DIR'],
            default_cover='/static/default-cover.png'
        )
        
        # 获取需要补充数据的图书
        # 条件：缺少封面、缺少详情、或缺少购买链接
        books = AwardBook.query.filter(
            (AwardBook.cover_local_path.is_(None)) |
            (AwardBook.cover_local_path == '/static/default-cover.png') |
            (AwardBook.details.is_(None)) |
            (AwardBook.buy_links.is_(None))
        ).limit(batch_size).all()
        
        if not books:
            print("✅ 所有图书数据已完整，无需补充")
            return
        
        print(f"📚 开始为 {len(books)} 本图书补充数据...")
        
        stats = {
            'cover_added': 0,
            'details_added': 0,
            'buy_links_added': 0,
            'failed': 0
        }
        
        for book in books:
            try:
                isbn = book.isbn13 or book.isbn10
                if not isbn:
                    print(f"⚠️ 图书无 ISBN: {book.title[:40]}...")
                    stats['failed'] += 1
                    continue
                
                print(f"🔍 处理: {book.title[:50]}...")
                
                # 从 Google Books 获取数据
                google_data = google_books.search_by_isbn(isbn)
                
                if not google_data:
                    print(f"  ⚠️ Google Books 未找到数据")
                    stats['failed'] += 1
                    continue
                
                updated = False
                
                # 1. 补充封面
                if (not book.cover_local_path or 
                    book.cover_local_path == '/static/default-cover.png'):
                    cover_url = google_data.get('cover_url')
                    if cover_url:
                        cached_path = image_cache.get_cached_image_url(cover_url)
                        if cached_path and cached_path != '/static/default-cover.png':
                            book.cover_original_url = cover_url
                            book.cover_local_path = cached_path
                            print(f"  ✅ 添加封面")
                            stats['cover_added'] += 1
                            updated = True
                
                # 2. 补充详情
                if not book.details and google_data.get('description'):
                    book.details = google_data['description']
                    print(f"  ✅ 添加详情")
                    stats['details_added'] += 1
                    updated = True
                
                # 3. 补充购买链接
                if not book.buy_links and google_data.get('buy_links'):
                    book.buy_links = json.dumps(google_data['buy_links'])
                    print(f"  ✅ 添加购买链接")
                    stats['buy_links_added'] += 1
                    updated = True
                
                if updated:
                    db.session.commit()
                    print(f"  💾 已保存")
                else:
                    print(f"  ℹ️ 无新数据")
                
                # 延迟避免请求过快
                import time
                time.sleep(0.5)
                
            except Exception as e:
                print(f"  ❌ 处理失败: {e}")
                stats['failed'] += 1
                continue
        
        print("\n" + "="*50)
        print("📊 补充结果:")
        print(f"  封面添加: {stats['cover_added']}")
        print(f"  详情添加: {stats['details_added']}")
        print(f"  购买链接添加: {stats['buy_links_added']}")
        print(f"  失败: {stats['failed']}")
        print("="*50)


if __name__ == '__main__':
    enrich_award_books(batch_size=20)
