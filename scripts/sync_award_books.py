#!/usr/bin/env python3
"""
图书数据同步脚本

通过 Google Books API 根据 ISBN 或书名获取真实图书信息，
包括封面图片，并下载到本地缓存。

用法:
    python scripts/sync_award_books.py
"""

import logging
import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import create_app
from app.models import db
from app.models.schemas import AwardBook
from app.services import GoogleBooksClient, ImageCacheService

# 配置日志
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s]: %(message)s', handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def sync_award_books():
    """同步所有获奖图书数据"""
    app = create_app('production')

    with app.app_context():
        # 创建 Google Books 客户端（不需要 API Key 也能使用）
        google_client = GoogleBooksClient(
            api_key=app.config.get('GOOGLE_API_KEY'), base_url='https://www.googleapis.com/books/v1/volumes', timeout=10
        )

        # 创建图片缓存服务
        image_cache = ImageCacheService(
            cache_dir=app.config['IMAGE_CACHE_DIR'], default_cover='/static/default-cover.png'
        )

        # 获取所有需要同步的图书
        books = AwardBook.query.all()
        logger.info(f'📚 开始同步 {len(books)} 本图书数据...')

        updated_count = 0
        failed_count = 0

        for i, book in enumerate(books, 1):
            try:
                logger.info(f'\n[{i}/{len(books)}] 处理: {book.title}')

                # 如果已经有本地封面，跳过
                if book.cover_local_path and book.cover_local_path != '/static/default-cover.png':
                    logger.info('  ✅ 已有本地封面，跳过')
                    continue

                # 获取封面 URL
                cover_url = google_client.get_cover_url(isbn=book.isbn13, title=book.title, author=book.author)

                if not cover_url:
                    logger.warning(f'  ⚠️ 未找到封面: {book.title}')
                    failed_count += 1
                    continue

                logger.info(f'  📷 找到封面: {cover_url[:60]}...')

                # 下载并缓存封面
                cached_url = image_cache.get_cached_image_url(cover_url, ttl=86400 * 365)  # 1年缓存

                if cached_url and cached_url != '/static/default-cover.png':
                    book.cover_original_url = cover_url
                    book.cover_local_path = cached_url
                    updated_count += 1
                    logger.info(f'  ✅ 封面已缓存: {cached_url}')
                else:
                    logger.warning('  ⚠️ 封面下载失败')
                    failed_count += 1

                # 每处理10本保存一次，避免数据丢失
                if i % 10 == 0:
                    db.session.commit()
                    logger.info(f'💾 已保存进度 ({i}/{len(books)})')

                # 添加延迟避免请求过快
                time.sleep(0.5)

            except Exception as e:
                logger.error(f'  ❌ 处理失败: {e}')
                failed_count += 1
                continue

        # 最终保存
        db.session.commit()

        logger.info(f'\n{"=" * 50}')
        logger.info('✅ 同步完成!')
        logger.info(f'📊 总计: {len(books)} 本')
        logger.info(f'✅ 成功: {updated_count} 本')
        logger.info(f'❌ 失败: {failed_count} 本')
        logger.info(f'⏭️ 跳过: {len(books) - updated_count - failed_count} 本')


if __name__ == '__main__':
    sync_award_books()
