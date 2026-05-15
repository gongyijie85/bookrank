#!/usr/bin/env python3
"""
检查获奖书单数据状态

查看当前数据库中的奖项和获奖图书统计
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app
from app.models import db
from app.models.schemas import Award, AwardBook, SystemConfig


def check_award_books():
    """检查获奖书单数据"""
    app = create_app('development')
    
    with app.app_context():
        print("=" * 60)
        print("📊 获奖书单数据检查")
        print("=" * 60)
        
        # 检查奖项数据
        awards = Award.query.all()
        print(f"\n🏆 奖项数量: {len(awards)}")
        for award in awards:
            book_count = award.books.count()
            displayable_count = award.books.filter_by(is_displayable=True).count()
            print(f"  - {award.name}: {book_count} 本 (可展示: {displayable_count} 本)")
        
        # 检查获奖图书总数
        total_books = AwardBook.query.count()
        displayable_books = AwardBook.query.filter_by(is_displayable=True).count()
        with_cover = AwardBook.query.filter(AwardBook.cover_local_path.isnot(None)).count()
        
        print(f"\n📚 获奖图书总数: {total_books}")
        print(f"   可展示: {displayable_books} 本")
        print(f"   有封面: {with_cover} 本")
        
        # 按年份统计
        print(f"\n📅 按年份统计:")
        years = db.session.query(AwardBook.year).distinct().order_by(AwardBook.year).all()
        for year_tuple in years:
            year = year_tuple[0]
            year_count = AwardBook.query.filter_by(year=year).count()
            print(f"  {year}年: {year_count} 本")
        
        # 检查刷新时间
        last_refresh = SystemConfig.get_value('award_books_last_refresh')
        print(f"\n🔄 上次刷新时间: {last_refresh if last_refresh else '从未刷新'}")
        
        print("\n" + "=" * 60)


if __name__ == '__main__':
    check_award_books()
