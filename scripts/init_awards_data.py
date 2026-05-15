#!/usr/bin/env python3
"""
国际图书奖项数据初始化脚本
创建奖项基础数据并导入示例图书数据
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from app.models.database import db
from app.models.schemas import Award, AwardBook


def init_awards():
    """初始化5大国际图书奖项"""
    awards_data = [
        {
            'id': 1,
            'name': '普利策奖',
            'name_en': 'Pulitzer Prize',
            'country': '美国',
            'description': '美国新闻界和文学界的最高荣誉，分为新闻奖、文学奖和音乐奖。文学奖包括小说、戏剧、历史、传记、诗歌和一般非虚构类作品。',
            'category_count': 6,
            'icon_class': 'fa-trophy',
            'established_year': 1917,
            'award_month': 5
        },
        {
            'id': 2,
            'name': '美国国家图书奖',
            'name_en': 'National Book Award',
            'country': '美国',
            'description': '美国文学界的重要奖项，设立于1950年，分为小说、非虚构、诗歌、青少年文学和翻译文学五个类别。',
            'category_count': 5,
            'icon_class': 'fa-book',
            'established_year': 1950,
            'award_month': 11
        },
        {
            'id': 3,
            'name': '布克奖',
            'name_en': 'Booker Prize',
            'country': '英国',
            'description': '英国最具声望的文学奖项，授予年度最佳英文小说。自1969年设立以来，已成为英语文学界最重要的奖项之一。',
            'category_count': 1,
            'icon_class': 'fa-star',
            'established_year': 1969,
            'award_month': 11
        },
        {
            'id': 4,
            'name': '雨果奖',
            'name_en': 'Hugo Award',
            'country': '美国',
            'description': '科幻文学界最高荣誉，以《惊奇故事》杂志创始人雨果·根斯巴克命名。评选范围包括最佳长篇小说、中篇小说、短篇小说等。',
            'category_count': 8,
            'icon_class': 'fa-rocket',
            'established_year': 1953,
            'award_month': 8
        },
        {
            'id': 5,
            'name': '诺贝尔文学奖',
            'name_en': 'Nobel Prize in Literature',
            'country': '瑞典',
            'description': '根据阿尔弗雷德·诺贝尔的遗嘱设立，授予在文学领域创作出具有理想倾向的最佳作品的人。是文学界最高荣誉之一。',
            'category_count': 1,
            'icon_class': 'fa-graduation-cap',
            'established_year': 1901,
            'award_month': 10
        }
    ]
    
    with app.app_context():
        # 清空现有数据
        AwardBook.query.delete()
        Award.query.delete()
        
        # 创建奖项
        for award_data in awards_data:
            award = Award(**award_data)
            db.session.add(award)
        
        db.session.commit()
        print(f"✅ 已创建 {len(awards_data)} 个奖项")


def init_sample_books():
    """初始化示例图书数据（2023-2025年部分数据）"""
    sample_books = [
        # 普利策奖 2023-2025
        {
            'award_id': 1, 'year': 2025, 'category': '小说',
            'title': 'The Maniac', 'author': 'Benjamín Labatut',
            'description': 'A novel exploring the life of John von Neumann and the dawn of the digital age.',
            'isbn13': '9780593654477'
        },
        {
            'award_id': 1, 'year': 2024, 'category': '小说',
            'title': 'The Night Watchman', 'author': 'Louise Erdrich',
            'description': 'A powerful novel about a community fighting to protect their land and way of life.',
            'isbn13': '9780062671196'
        },
        {
            'award_id': 1, 'year': 2023, 'category': '小说',
            'title': 'Trust', 'author': 'Hernan Diaz',
            'description': 'A novel about wealth, family, and the American Dream in the 1920s.',
            'isbn13': '9780593420317'
        },
        
        # 布克奖 2023-2025
        {
            'award_id': 3, 'year': 2025, 'category': '小说',
            'title': 'Orbital', 'author': 'Samantha Harvey',
            'description': 'A novel set in space, exploring human connection and isolation.',
            'isbn13': '9780802163673'
        },
        {
            'award_id': 3, 'year': 2024, 'category': '小说',
            'title': 'Prophet Song', 'author': 'Paul Lynch',
            'description': 'A dystopian novel about a mother trying to keep her family together in a collapsing Ireland.',
            'isbn13': '9780802163628'
        },
        {
            'award_id': 3, 'year': 2023, 'category': '小说',
            'title': 'The Seven Moons of Maali Almeida', 'author': 'Shehan Karunatilaka',
            'description': 'A darkly comic novel about a war photographer navigating the afterlife.',
            'isbn13': '9781324091704'
        },
        
        # 诺贝尔文学奖 2023-2025
        {
            'award_id': 5, 'year': 2025, 'category': '文学',
            'title': 'The Years', 'author': 'Annie Ernaux',
            'description': 'A collective autobiography exploring the passage of time and social change.',
            'isbn13': '9781609809511'
        },
        {
            'award_id': 5, 'year': 2024, 'category': '文学',
            'title': 'Time Shelter', 'author': 'Georgi Gospodinov',
            'description': 'A novel about a clinic that recreates past decades to help Alzheimer patients.',
            'isbn13': '9781324091705'
        },
        {
            'award_id': 5, 'year': 2023, 'category': '文学',
            'title': 'The Piano Teacher', 'author': 'Elfriede Jelinek',
            'description': 'A controversial novel exploring power dynamics and repression in post-war Austria.',
            'isbn13': '9780802143291'
        },
        
        # 雨果奖 2023-2025
        {
            'award_id': 4, 'year': 2025, 'category': '最佳长篇小说',
            'title': 'Project Hail Mary', 'author': 'Andy Weir',
            'description': 'A lone astronaut must save Earth from an extinction-level threat.',
            'isbn13': '9780593135204'
        },
        {
            'award_id': 4, 'year': 2024, 'category': '最佳长篇小说',
            'title': 'The World We Make', 'author': 'N. K. Jemisin',
            'description': 'A powerful conclusion to the Great Cities Duology.',
            'isbn13': '9780316509885'
        },
        {
            'award_id': 4, 'year': 2023, 'category': '最佳长篇小说',
            'title': 'A Memory Called Empire', 'author': 'Arkady Martine',
            'description': 'An ambassador arrives at the center of a vast empire and finds herself in danger.',
            'isbn13': '9781250186430'
        },
        
        # 美国国家图书奖 2023-2025
        {
            'award_id': 2, 'year': 2025, 'category': '小说',
            'title': 'The Rabbit Hutch', 'author': 'Tess Gunty',
            'description': 'A debut novel about loneliness and connection in a small Indiana city.',
            'isbn13': '9780593420318'
        },
        {
            'award_id': 2, 'year': 2024, 'category': '小说',
            'title': 'The Birdcatcher', 'author': 'Gayl Jones',
            'description': 'A novel about art, obsession, and the creative process.',
            'isbn13': '9780807007166'
        },
        {
            'award_id': 2, 'year': 2023, 'category': '小说',
            'title': 'Hell of a Book', 'author': 'Jason Mott',
            'description': 'A novel about a Black author on a cross-country publicity tour.',
            'isbn13': '9780593239917'
        },
    ]
    
    with app.app_context():
        for book_data in sample_books:
            book = AwardBook(**book_data)
            db.session.add(book)
        
        db.session.commit()
        print(f"✅ 已创建 {len(sample_books)} 本示例图书")


def main():
    """主函数"""
    print("🚀 开始初始化国际图书奖项数据...")
    print("-" * 50)
    
    try:
        init_awards()
        init_sample_books()
        
        print("-" * 50)
        print("✅ 数据初始化完成！")
        print("\n📊 数据概览:")
        
        with app.app_context():
            awards_count = Award.query.count()
            books_count = AwardBook.query.count()
            print(f"  - 奖项数量: {awards_count}")
            print(f"  - 图书数量: {books_count}")
            
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
