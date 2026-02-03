#!/usr/bin/env python3
"""检查获奖图书数据"""

from app import create_app
from app.models.schemas import AwardBook

app = create_app()

with app.app_context():
    books = AwardBook.query.all()
    
    print(f"共有 {len(books)} 本获奖图书\n")
    
    for book in books[:5]:
        print(f"📚 {book.title}")
        print(f"   作者: {book.author}")
        print(f"   ISBN: {book.isbn13}")
        print(f"   本地封面: {book.cover_local_path}")
        print(f"   原始封面: {book.cover_original_url}")
        print(f"   详细介绍: {book.details[:100] if book.details else 'None'}...")
        print(f"   购买链接: {book.buy_links}")
        print()
