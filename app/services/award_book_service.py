"""
获奖图书管理服务

提供获奖图书的自动刷新、增量更新、数据清理等功能
支持从 Wikidata 和 Open Library API 获取最新数据
"""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

import json
from ..models import db
from ..models.schemas import Award, AwardBook, SystemConfig
from .api_client import WikidataClient, OpenLibraryClient, ImageCacheService, GoogleBooksClient

logger = logging.getLogger(__name__)


class AwardBookService:
    """
    获奖图书管理服务
    
    功能：
    - 智能刷新：根据上次刷新时间决定是否刷新
    - 增量更新：只更新新增或变更的图书
    - 封面获取：自动从 API 获取封面图片
    - 数据清理：清理过期或无效数据
    """
    
    # 奖项名称映射 (Wikidata key -> 数据库名称)
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
    
    def __init__(self, app=None):
        self.app = app
        self.wikidata_client = WikidataClient(timeout=30)
        self.openlib_client = OpenLibraryClient(timeout=10)
        self.google_books_client = GoogleBooksClient(timeout=10)
        
        if app:
            self.image_cache = ImageCacheService(
                cache_dir=app.config['IMAGE_CACHE_DIR'],
                default_cover='/static/default-cover.png'
            )
        else:
            self.image_cache = None
    
    def should_refresh(self, force: bool = False, refresh_interval_days: int = 7) -> bool:
        """
        检查是否需要刷新数据
        
        Args:
            force: 强制刷新
            refresh_interval_days: 刷新间隔天数
            
        Returns:
            是否需要刷新
        """
        if force:
            return True
        
        # 获取上次刷新时间
        last_refresh = SystemConfig.get_value('award_books_last_refresh')
        
        if not last_refresh:
            logger.info("🔄 首次运行，需要刷新数据")
            return True
        
        try:
            last_refresh_time = datetime.fromisoformat(last_refresh)
            next_refresh_time = last_refresh_time + timedelta(days=refresh_interval_days)
            
            if datetime.now() >= next_refresh_time:
                logger.info(f"🔄 距离上次刷新已超过 {refresh_interval_days} 天，需要刷新")
                return True
            else:
                days_left = (next_refresh_time - datetime.now()).days
                logger.info(f"⏭️ 距离下次刷新还有 {days_left} 天")
                return False
                
        except Exception as e:
            logger.warning(f"⚠️ 解析上次刷新时间失败: {e}")
            return True
    
    def update_refresh_time(self):
        """更新上次刷新时间"""
        SystemConfig.set_value('award_books_last_refresh', datetime.now().isoformat())
        db.session.commit()
        logger.info("✅ 已更新刷新时间")
    
    def refresh_award_books(self, award_keys: List[str] = None, 
                           start_year: int = 2020, 
                           end_year: int = 2025,
                           force: bool = False) -> Dict[str, Any]:
        """
        刷新获奖图书数据
        
        Args:
            award_keys: 要刷新的奖项列表，None 表示所有
            start_year: 开始年份
            end_year: 结束年份
            force: 强制刷新
            
        Returns:
            刷新结果统计
        """
        if not self.should_refresh(force):
            return {'status': 'skipped', 'message': '未达到刷新时间'}
        
        if award_keys is None:
            award_keys = list(self.AWARD_NAME_MAP.keys())
        
        logger.info(f"🚀 开始刷新 {len(award_keys)} 个奖项的图书数据 ({start_year}-{end_year})...")
        
        stats = {
            'total_awards': len(award_keys),
            'processed_awards': 0,
            'new_books': 0,
            'updated_books': 0,
            'failed_books': 0,
            'errors': []
        }
        
        try:
            # 从 Wikidata 获取数据
            award_books_data = self.wikidata_client.get_all_award_books(
                awards=award_keys,
                start_year=start_year,
                end_year=end_year
            )
            
            # 处理每个奖项
            for award_key, books_data in award_books_data.items():
                try:
                    result = self._process_award_books(award_key, books_data)
                    stats['new_books'] += result['new']
                    stats['updated_books'] += result['updated']
                    stats['failed_books'] += result['failed']
                    stats['processed_awards'] += 1
                except Exception as e:
                    error_msg = f"处理 {award_key} 失败: {e}"
                    logger.error(error_msg)
                    stats['errors'].append(error_msg)
            
            # 更新刷新时间
            self.update_refresh_time()
            
            logger.info(f"✅ 刷新完成: 新增 {stats['new_books']} 本, 更新 {stats['updated_books']} 本")
            
        except Exception as e:
            error_msg = f"刷新过程出错: {e}"
            logger.error(error_msg)
            stats['errors'].append(error_msg)
        
        return stats
    
    def _process_award_books(self, award_key: str, books_data: List[Dict]) -> Dict[str, int]:
        """
        处理单个奖项的图书数据
        
        Args:
            award_key: 奖项键名
            books_data: 图书数据列表
            
        Returns:
            处理结果统计
        """
        result = {'new': 0, 'updated': 0, 'failed': 0}
        
        award_name = self.AWARD_NAME_MAP.get(award_key, award_key)
        category = self.AWARD_CATEGORY_MAP.get(award_key, '其他')
        
        # 获取或创建奖项
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
        for book_data in books_data:
            try:
                process_result = self._process_single_book(award, book_data, category)
                result[process_result] += 1
            except Exception as e:
                logger.error(f"处理图书失败 {book_data.get('title')}: {e}")
                result['failed'] += 1
            
            # 延迟避免请求过快
            time.sleep(0.3)
        
        db.session.commit()
        return result
    
    def _process_single_book(self, award: Award, book_data: Dict, category: str) -> str:
        """
        处理单本图书
        
        Args:
            award: 奖项对象
            book_data: 图书数据
            category: 类别
            
        Returns:
            处理结果: 'new', 'updated', 'skipped'
        """
        isbn = book_data.get('isbn13') or book_data.get('isbn10')
        if not isbn:
            logger.warning(f"⚠️ 图书无 ISBN: {book_data.get('title')}")
            return 'failed'
        
        # 检查是否已存在
        existing = AwardBook.query.filter_by(
            award_id=award.id,
            isbn13=isbn if len(isbn) == 13 else None
        ).first()
        
        if existing:
            # 检查是否需要更新
            needs_update = False
            
            if not existing.cover_local_path and self.image_cache:
                # 尝试获取封面
                cover_url = self._get_cover_url(isbn)
                if cover_url:
                    cached_path = self.image_cache.get_cached_image_url(cover_url)
                    if cached_path and cached_path != '/static/default-cover.png':
                        existing.cover_original_url = cover_url
                        existing.cover_local_path = cached_path
                        needs_update = True
            
            if needs_update:
                db.session.commit()
                logger.info(f"🔄 更新图书: {existing.title[:40]}...")
                return 'updated'
            
            return 'skipped'
        
        # 获取图书详情 (Open Library)
        book_details = self.openlib_client.fetch_book_by_isbn(isbn)
        
        # 获取 Google Books 数据（详细信息和购买链接）
        google_books_data = self.google_books_client.search_by_isbn(isbn)
        
        # 获取封面（优先 Open Library，后补 Google Books）
        cover_url = self._get_cover_url(isbn)
        
        # 如果 Open Library 没有封面，尝试 Google Books
        if not cover_url and google_books_data.get('cover_url'):
            cover_url = google_books_data['cover_url']
            logger.info(f"📚 从 Google Books 获取封面: {book_data['title'][:40]}...")
        
        cover_local_path = None
        if cover_url and self.image_cache:
            cover_local_path = self.image_cache.get_cached_image_url(cover_url)
            if cover_local_path == '/static/default-cover.png':
                cover_local_path = None
        
        # 提取描述信息（优先使用更详细的来源）
        def get_description(preferred_source, fallback_source, default_msg):
            """获取描述，优先使用指定来源"""
            desc = preferred_source.get('description')
            if desc and len(desc) > 50:
                return desc
            desc = fallback_source.get('description')
            if desc and len(desc) > 50:
                return desc
            return default_msg
        
        description = get_description(book_details, google_books_data, f'{award.name}获奖作品')
        details = get_description(google_books_data, book_details, '')
        
        # 获取购买链接
        buy_links = google_books_data.get('buy_links', {})
        
        # 创建新图书记录
        book = AwardBook(
            award_id=award.id,
            year=book_data['year'],
            category=category,
            rank=1,
            title=book_data['title'],
            author=book_data.get('author') or book_details.get('author') or google_books_data.get('author') or 'Unknown',
            description=description,
            details=details,
            isbn13=isbn if len(isbn) == 13 else None,
            isbn10=isbn if len(isbn) == 10 else None,
            cover_original_url=cover_url,
            cover_local_path=cover_local_path,
            buy_links=json.dumps(buy_links) if buy_links else None
        )
        
        db.session.add(book)
        logger.info(f"✅ 新增图书: {book.title[:40]}...")
        return 'new'
    
    def _get_cover_url(self, isbn: str) -> Optional[str]:
        """获取封面 URL（优先 Open Library，后补 Google Books）"""
        # 尝试 Open Library
        cover_url = self.openlib_client.get_cover_url(isbn, size='L')
        if cover_url:
            return cover_url
        
        # TODO: 如果需要，可以添加 Google Books 作为备用
        return None
    
    def fetch_missing_covers(self, batch_size: int = 10) -> Dict[str, int]:
        """
        为缺失封面的图书获取封面
        
        Args:
            batch_size: 每批处理数量
            
        Returns:
            处理结果统计
        """
        if not self.image_cache:
            logger.error("❌ ImageCacheService 未初始化")
            return {'success': 0, 'failed': 0}
        
        # 获取缺失封面的图书
        books = AwardBook.query.filter(
            (AwardBook.cover_local_path.is_(None)) | 
            (AwardBook.cover_local_path == '/static/default-cover.png')
        ).limit(batch_size).all()
        
        if not books:
            logger.info("✅ 所有图书已有封面")
            return {'success': 0, 'failed': 0}
        
        logger.info(f"📚 开始为 {len(books)} 本图书获取封面...")
        
        stats = {'success': 0, 'failed': 0}
        
        for book in books:
            try:
                isbn = book.isbn13 or book.isbn10
                if not isbn:
                    continue
                
                cover_url = self._get_cover_url(isbn)
                if not cover_url:
                    stats['failed'] += 1
                    continue
                
                cached_path = self.image_cache.get_cached_image_url(cover_url)
                if cached_path and cached_path != '/static/default-cover.png':
                    book.cover_original_url = cover_url
                    book.cover_local_path = cached_path
                    stats['success'] += 1
                    logger.info(f"✅ {book.title[:40]}...")
                else:
                    stats['failed'] += 1
                
                time.sleep(0.3)
                
            except Exception as e:
                logger.error(f"❌ 获取封面失败: {e}")
                stats['failed'] += 1
        
        db.session.commit()
        logger.info(f"✅ 封面获取完成: 成功 {stats['success']} 本, 失败 {stats['failed']} 本")
        
        return stats
    
    def get_refresh_status(self) -> Dict[str, Any]:
        """获取刷新状态"""
        last_refresh = SystemConfig.get_value('award_books_last_refresh')
        
        if not last_refresh:
            return {
                'last_refresh': None,
                'next_refresh': None,
                'days_since_last': None,
                'needs_refresh': True
            }
        
        try:
            last_time = datetime.fromisoformat(last_refresh)
            next_time = last_time + timedelta(days=7)
            days_since = (datetime.now() - last_time).days
            
            return {
                'last_refresh': last_refresh,
                'next_refresh': next_time.isoformat(),
                'days_since_last': days_since,
                'needs_refresh': days_since >= 7
            }
        except:
            return {
                'last_refresh': last_refresh,
                'next_refresh': None,
                'days_since_last': None,
                'needs_refresh': True
            }
