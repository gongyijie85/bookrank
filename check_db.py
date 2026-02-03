#!/usr/bin/env python3
"""检查数据库内容"""

from app import create_app
from app.models.schemas import Award, AwardBook

app = create_app()

with app.app_context():
    award_count = Award.query.count()
    book_count = AwardBook.query.count()
    
    print(f"数据库状态:")
    print(f"  Awards: {award_count}")
    print(f"  Books: {book_count}")
    
    if award_count > 0:
        print("\n奖项列表:")
        for award in Award.query.all():
            print(f"  - {award.name}")
    
    if book_count > 0:
        print("\n图书列表 (前5本):")
        for book in AwardBook.query.limit(5).all():
            print(f"  - {book.title} ({book.year})")
