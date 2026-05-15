#!/usr/bin/env python3
"""
优化获奖书单数据

1. 为所有图书获取封面
2. 标记可展示状态
3. 补充缺失数据
"""

import sys
import time
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app
from app.models import db
from app.models.schemas import AwardBook
from app.services import GoogleBooksClient, ImageCacheService


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def optimize_award_books():
    """优化获奖书单数据"""
    app = create_app('development')
    
    with app.app_context():
        print("=" * 60)
        print("🚀 开始优化获奖书单数据")
        print("=" * 60)
        
        # 创建客户端
        google_client = GoogleBooksClient(
            api_key=app.config.get('GOOGLE_API_KEY'),
            base_url='https://www.googleapis.com/books/v1/volumes',
            timeout=15
        )
        
        image_cache = ImageCacheService(
            cache_dir=app.config['IMAGE_CACHE_DIR'],
            default_cover='/static/default-cover.png'
        )
        
        # 获取所有需要处理的图书
        books = AwardBook.query.all()
        logger.info(f"\n📚 待处理图书: {len(books)} 本")
        
        stats = {
            'cover_added': 0,
            'cover_failed': 0,
            'marked_displayable': 0,
            'skipped': 0
        }
        
        for i, book in enumerate(books, 1):
            try:
                logger.info(f"\n[{i}/{len(books)}] 处理: {book.title[:50]}")
                
                # 1. 获取封面（如果没有）
                if not book.cover_local_path or book.cover_local_path == '/static/default-cover.png':
                    logger.info(f"  📷 获取封面...")
                    
                    # 尝试从 Google Books 获取封面
                    cover_url = google_client.get_cover_url(
                        isbn=book.isbn13,
                        title=book.title,
                        author=book.author
                    )
                    
                    if cover_url:
                        logger.info(f"  ✅ 找到封面: {cover_url[:60]}...")
                        
                        # 下载并缓存封面
                        cached_url = image_cache.get_cached_image_url(cover_url, ttl=86400*365)
                        
                        if cached_url and cached_url != '/static/default-cover.png':
                            book.cover_original_url = cover_url
                            book.cover_local_path = cached_url
                            stats['cover_added'] += 1
                            logger.info(f"  ✅ 封面已缓存")
                        else:
                            stats['cover_failed'] += 1
                            logger.warning(f"  ⚠️ 封面下载失败")
                    else:
                        stats['cover_failed'] += 1
                        logger.warning(f"  ⚠️ 未找到封面")
                else:
                    stats['skipped'] += 1
                    logger.info(f"  ✅ 已有封面，跳过")
                
                # 2. 标记为可展示（只要有基本信息）
                if not book.is_displayable:
                    if book.title and book.author and (book.isbn13 or book.isbn10):
                        book.is_displayable = True
                        book.verification_status = 'verified'
                        stats['marked_displayable'] += 1
                        logger.info(f"  ✅ 标记为可展示")
                
                # 每5本保存一次
                if i % 5 == 0:
                    db.session.commit()
                    logger.info(f"💾 已保存进度 ({i}/{len(books)})")
                
                # 延迟避免请求过快
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"  ❌ 处理失败: {e}")
                stats['cover_failed'] += 1
                continue
        
        # 最终保存
        db.session.commit()
        
        print("\n" + "=" * 60)
        print("✅ 优化完成!")
        print("=" * 60)
        print(f"📊 统计:")
        print(f"   新增封面: {stats['cover_added']} 本")
        print(f"   封面失败: {stats['cover_failed']} 本")
        print(f"   标记可展示: {stats['marked_displayable']} 本")
        print(f"   跳过: {stats['skipped']} 本")
        print("=" * 60)


if __name__ == '__main__':
    optimize_award_books()
