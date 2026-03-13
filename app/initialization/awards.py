"""
奖项数据初始化模块
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


AWARDS_FALLBACK_DATA = {
    'pulitzer_fiction': {
        'name': '普利策奖',
        'name_en': 'Pulitzer Prize',
        'country': '美国',
        'description': '美国新闻界和文学界的最高荣誉，分为新闻奖、文学奖和音乐奖。文学奖包括小说、戏剧、历史、传记、诗歌和一般非虚构类作品.',
        'category_count': 6,
        'icon_class': 'fa-trophy',
        'established_year': 1917,
        'award_month': 5
    },
    'booker': {
        'name': '布克奖',
        'name_en': 'Booker Prize',
        'country': '英国',
        'description': '英国最具声望的文学奖项，授予年度最佳英文小说。自1969年设立以来，已成为英语文学界最重要的奖项之一.',
        'category_count': 1,
        'icon_class': 'fa-star',
        'established_year': 1969,
        'award_month': 11
    },
    'hugo': {
        'name': '雨果奖',
        'name_en': 'Hugo Award',
        'country': '美国',
        'description': '科幻文学界最高荣誉，以《惊奇故事》杂志创始人雨果·根斯巴克命名.评选范围包括最佳长篇小说、中篇小说、短篇小说等.',
        'category_count': 8,
        'icon_class': 'fa-rocket',
        'established_year': 1953,
        'award_month': 8
    },
    'nobel_literature': {
        'name': '诺贝尔文学奖',
        'name_en': 'Nobel Prize in Literature',
        'country': '瑞典',
        'description': '根据阿尔弗雷德·诺贝尔的遗嘱设立,授予在文学领域创作出具有理想倾向的最佳作品的人.是文学界最高荣誉之一.',
        'category_count': 1,
        'icon_class': 'fa-graduation-cap',
        'established_year': 1901,
        'award_month': 10
    },
    'nebula': {
        'name': '星云奖',
        'name_en': 'Nebula Award',
        'country': '美国',
        'description': '美国科幻和奇幻作家协会颁发的年度大奖，与雨果奖并称为科幻界双璧.评选范围包括最佳长篇小说、中篇小说、短篇小说等.',
        'category_count': 6,
        'icon_class': 'fa-star',
        'established_year': 1965,
        'award_month': 5
    },
    'international_booker': {
        'name': '国际布克奖',
        'name_en': 'International Booker Prize',
        'country': '英国',
        'description': '布克奖的姊妹奖项，专门颁发给翻译成英语并在英国出版的外国小说.作者和译者平分奖金，是挖掘非英语佳作的重要风向标.',
        'category_count': 1,
        'icon_class': 'fa-globe',
        'established_year': 2005,
        'award_month': 5
    },
    'edgar': {
        'name': '爱伦·坡奖',
        'name_en': 'Edgar Award',
        'country': '美国',
        'description': '美国推理作家协会颁发的年度大奖，以推理小说之父爱伦·坡命名.是推理小说界的最高荣誉，涵盖小说、电视、电影等多个领域.',
        'category_count': 12,
        'icon_class': 'fa-user-secret',
        'established_year': 1946,
        'award_month': 4
    },
}


def init_awards_data(app):
    """
    自动初始化奖项数据（从Wikidata动态获取，Render免费版优化）
    
    优化策略：
    1. 如果数据已存在，快速返回
    2. Wikidata API超时设置为10秒（Render端口扫描限制）
    3. API失败时使用fallback数据
    """
    try:
        from ..models.schemas import Award, AwardBook
        from ..models.new_book import Publisher, NewBook
        from ..services import WikidataClient
        from ..models.database import db
        
        app.logger.info("🚀 开始检查奖项数据...")
        
        award_count = 0
        book_count = 0
        publisher_count = 0
        new_book_count = 0
        try:
            award_count = Award.query.count()
            book_count = AwardBook.query.count()
            publisher_count = Publisher.query.count()
            new_book_count = NewBook.query.count()
        except Exception as e:
            error_msg = str(e).lower()
            if "no such column" in error_msg or "no such table" in error_msg:
                app.logger.warning(f"⚠️ 数据库表结构已改变: {e}")
                app.logger.info("🔄 重新创建数据库表...")
                db.drop_all()
                db.create_all()
            else:
                app.logger.error(f"❌ 数据库查询失败: {e}")
                raise
        
        app.logger.info(f"📊 当前数据: {award_count} 个奖项, {book_count} 本图书, {publisher_count} 个出版社, {new_book_count} 本新书")
        
        # 检查所有必要的表是否存在
        if award_count >= 5 and book_count >= 12 and publisher_count >= 2:
            app.logger.info(f"✅ 基础数据已完整")
            app.logger.info("⏭️ 跳过自动补充，将在用户查看详情时按需获取")
            return
        
        if award_count == 0 and book_count == 0 and publisher_count == 0:
            app.logger.info("🆕 数据库为空，开始初始化基础数据...")
        else:
            app.logger.info(f"⚠️ 数据不完整，补充数据...")
        
        # 使用fallback数据直接初始化，避免启动时API调用超时
        app.logger.info("📝 使用本地数据初始化奖项...")
        
        awards_data = []
        for award_key, fallback_data in AWARDS_FALLBACK_DATA.items():
            merged_data = {
                'name': fallback_data['name'],
                'name_en': fallback_data['name_en'],
                'country': fallback_data['country'],
                'description': fallback_data['description'],
                'category_count': fallback_data['category_count'],
                'icon_class': fallback_data['icon_class'],
                'established_year': fallback_data['established_year'],
                'award_month': fallback_data['award_month'],
                'wikidata_id': None
            }
            awards_data.append(merged_data)
        
        created_awards = 0
        for award_data in awards_data:
            existing = Award.query.filter_by(name=award_data['name']).first()
            if not existing:
                award = Award(**award_data)
                db.session.add(award)
                created_awards += 1
        
        if created_awards > 0:
            db.session.commit()
            app.logger.info(f"✅ 已创建 {created_awards} 个新奖项")
        else:
            app.logger.info("✅ 所有奖项已存在")
        
        # 初始化出版社数据
        app.logger.info("📝 初始化出版社数据...")
        from ..services.new_book_service import NewBookService
        
        service = NewBookService()
        publisher_count = service.init_publishers()
        app.logger.info(f"✅ 已初始化 {publisher_count} 个出版社")
        
        # 初始化预置获奖图书数据（Render 免费版优化）
        app.logger.info("📚 检查预置获奖图书...")
        from .sample_award_books import init_sample_award_books
        init_sample_award_books(app)
        
    except Exception as e:
        app.logger.error(f"❌ 初始化奖项数据失败: {e}", exc_info=True)
