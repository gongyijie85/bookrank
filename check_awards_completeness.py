#!/usr/bin/env python3
"""
检查获奖图书2022-2025年完整性
"""

from app import create_app
from app.models.schemas import AwardBook, Award
from collections import defaultdict

app = create_app()

def check_awards_completeness():
    """检查各奖项2022-2025年的完整性"""
    
    with app.app_context():
        # 获取所有获奖图书
        books = AwardBook.query.all()
        
        # 按奖项和年份分组
        awards_data = defaultdict(lambda: defaultdict(list))
        
        for book in books:
            award_name = book.award.name if book.award else 'Unknown'
            year = book.year
            awards_data[award_name][year].append({
                'title': book.title,
                'author': book.author,
                'category': book.category,
                'isbn13': book.isbn13
            })
        
        # 定义期望的奖项列表
        expected_awards = [
            '普利策奖',
            '布克奖', 
            '诺贝尔文学奖',
            '雨果奖',
            '美国国家图书奖',
            '星云奖',
            '国际布克奖',
            '爱伦·坡奖'
        ]
        
        # 检查年份范围
        years = [2022, 2023, 2024, 2025]
        
        print("=" * 100)
        print("获奖图书完整性检查 (2022-2025年)")
        print("=" * 100)
        
        for award_name in expected_awards:
            print(f"\n📚 {award_name}")
            print("-" * 100)
            
            if award_name not in awards_data:
                print(f"   ❌ 该奖项没有任何数据")
                continue
            
            award_years = awards_data[award_name]
            
            for year in years:
                books_in_year = award_years.get(year, [])
                
                if books_in_year:
                    print(f"   {year}年: ✅ {len(books_in_year)} 本")
                    for book in books_in_year:
                        print(f"      - {book['title']} ({book['category']})")
                else:
                    print(f"   {year}年: ❌ 缺失")
        
        # 统计汇总
        print("\n" + "=" * 100)
        print("统计汇总")
        print("=" * 100)
        
        total_books = len(books)
        print(f"\n总计: {total_books} 本获奖图书")
        
        for award_name in expected_awards:
            if award_name in awards_data:
                award_years = awards_data[award_name]
                total_in_award = sum(len(books) for books in award_years.values())
                years_count = len(award_years)
                print(f"  {award_name}: {total_in_award} 本 ({years_count} 个年份)")
            else:
                print(f"  {award_name}: 0 本")
        
        # 检查缺失项
        print("\n" + "=" * 100)
        print("缺失项检查")
        print("=" * 100)
        
        missing_items = []
        
        for award_name in expected_awards:
            if award_name not in awards_data:
                for year in years:
                    missing_items.append(f"{award_name} {year}年")
            else:
                award_years = awards_data[award_name]
                for year in years:
                    if year not in award_years:
                        missing_items.append(f"{award_name} {year}年")
        
        if missing_items:
            print(f"\n发现 {len(missing_items)} 个缺失项:")
            for item in missing_items:
                print(f"  - {item}")
        else:
            print("\n✅ 所有奖项2022-2025年数据齐全")

if __name__ == '__main__':
    check_awards_completeness()
