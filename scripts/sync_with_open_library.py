#!/usr/bin/env python3
"""
Open Library 数据同步脚本

通过 Open Library API 根据 ISBN 获取真实图书信息，
包括封面图片，并下载到本地缓存。

Open Library 优势：
- 完全免费，无需 API Key
- 支持通过 ISBN 查询图书
- 提供封面图片服务
- 返回 JSON 格式数据

用法:
    python scripts/sync_with_open_library.py
"""

import os
import sys
import time
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import create_app
from app.models import db
from app.models.schemas import AwardBook
from app.services import OpenLibraryClient, ImageCacheService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def sync_with_open_library():
    """通过 Open Library API 同步所有获奖图书数据"""
    app = create_app('production')
    
    with app.app_context():
        # 创建 Open Library 客户端
        openlib_client = OpenLibraryClient(timeout=10)
        
        # 创建图片缓存服务
        image_cache = ImageCacheService(
            cache_dir=app.config['IMAGE_CACHE_DIR'],
            default_cover='/static/default-cover.png'
        )
        
        # 获取所有需要同步的图书
        books = AwardBook.query.all()
        logger.info(f"📚 开始通过 Open Library 同步 {len(books)} 本图书数据...")
        
        updated_count = 0
        failed_count = 0
        skipped_count = 0
        
        for i, book in enumerate(books, 1):
            try:
                logger.info(f"\n[{i}/{len(books)}] 处理: {book.title}")
                
                # 如果已经有本地封面且信息完整，跳过
                if (book.cover_local_path and 
                    book.cover_local_path != '/static/default-cover.png' and
                    book.description and len(book.description) > 50):
                    logger.info(f"  ✅ 数据已完整，跳过")
                    skipped_count += 1
                    continue
                
                if not book.isbn13:
                    logger.warning(f"  ⚠️ 无 ISBN，跳过")
                    skipped_count += 1
                    continue
                
                # 通过 Open Library API 获取图书详情
                book_data = openlib_client.fetch_book_by_isbn(book.isbn13)
                
                if not book_data:
                    logger.warning(f"  ⚠️ Open Library 未找到数据: {book.title}")
                    failed_count += 1
                    continue
                
                logger.info(f"  📖 找到数据: {book_data.get('title', 'N/A')}")
                
                # 更新图书信息
                updated = False
                
                # 更新描述（如果 Open Library 的描述更长）
                if book_data.get('description'):
                    new_desc = book_data['description']
                    old_desc = book.description or ''
                    if len(new_desc) > len(old_desc):
                        book.description = new_desc
                        updated = True
                        logger.info(f"  📝 更新描述")
                
                # 更新作者信息（如果缺失）
                if book_data.get('author') and not book.author:
                    book.author = book_data['author']
                    updated = True
                    logger.info(f"  👤 更新作者")
                
                # 获取并缓存封面
                if not book.cover_local_path or book.cover_local_path == '/static/default-cover.png':
                    # 首先尝试从 API 返回的 cover_url 获取
                    cover_url = book_data.get('cover_url')
                    
                    # 如果 API 没有返回封面，尝试构建封面 URL
                    if not cover_url:
                        cover_url = openlib_client.get_cover_url(book.isbn13, size='L')
                    
                    if cover_url:
                        logger.info(f"  📷 找到封面: {cover_url[:60]}...")
                        
                        # 下载并缓存封面
                        cached_url = image_cache.get_cached_image_url(cover_url, ttl=86400*365)
                        
                        if cached_url and cached_url != '/static/default-cover.png':
                            book.cover_original_url = cover_url
                            book.cover_local_path = cached_url
                            updated = True
                            logger.info(f"  ✅ 封面已缓存")
                        else:
                            logger.warning(f"  ⚠️ 封面下载失败")
                    else:
                        logger.warning(f"  ⚠️ 未找到封面")
                
                if updated:
                    updated_count += 1
                
                # 每处理5本保存一次，避免数据丢失
                if i % 5 == 0:
                    db.session.commit()
                    logger.info(f"💾 已保存进度 ({i}/{len(books)})")
                
                # 添加延迟避免请求过快（Open Library 限制较宽松，但仍需礼貌）
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"  ❌ 处理失败: {e}")
                failed_count += 1
                continue
        
        # 最终保存
        db.session.commit()
        
        logger.info(f"\n{'='*50}")
        logger.info(f"✅ Open Library 同步完成!")
        logger.info(f"📊 总计: {len(books)} 本")
        logger.info(f"✅ 成功更新: {updated_count} 本")
        logger.info(f"⏭️ 跳过: {skipped_count} 本")
        logger.info(f"❌ 失败: {failed_count} 本")


def verify_isbns():
    """验证所有图书的 ISBN 是否有效"""
    app = create_app('production')
    
    with app.app_context():
        openlib_client = OpenLibraryClient(timeout=10)
        
        books = AwardBook.query.all()
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
                    # 对比标题是否匹配（允许一定差异）
                    api_title = book_data['title'].lower().replace(' ', '')
                    db_title = book.title.lower().replace(' ', '')
                    
                    if api_title == db_title or api_title in db_title or db_title in api_title:
                        logger.info(f"[{i}/{len(books)}] ✅ {book.title}: ISBN 有效")
                        valid_count += 1
                    else:
                        logger.warning(f"[{i}/{len(books)}] ⚠️ {book.title}: 标题不匹配")
                        logger.warning(f"    数据库: {book.title}")
                        logger.warning(f"    API: {book_data['title']}")
                        invalid_count += 1
                else:
                    logger.warning(f"[{i}/{len(books)}] ❌ {book.title}: ISBN 无效或不存在")
                    invalid_count += 1
                
                time.sleep(0.3)
                
            except Exception as e:
                logger.error(f"[{i}/{len(books)}] ❌ {book.title}: 验证失败 - {e}")
                invalid_count += 1
        
        logger.info(f"\n{'='*50}")
        logger.info(f"✅ ISBN 验证完成!")
        logger.info(f"✅ 有效: {valid_count} 本")
        logger.info(f"❌ 无效: {invalid_count} 本")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Open Library 数据同步工具')
    parser.add_argument('--verify', action='store_true', 
                        help='仅验证 ISBN，不更新数据')
    parser.add_argument('--sync', action='store_true',
                        help='同步数据（默认）')
    
    args = parser.parse_args()
    
    if args.verify:
        verify_isbns()
    else:
        sync_with_open_library()
