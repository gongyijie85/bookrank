#!/usr/bin/env python3
"""
修正错误的 ISBN
"""

import requests

def search_openlib(title, author):
    """搜索 Open Library 获取正确的 ISBN"""
    try:
        query = f"{title} {author}".replace(' ', '+')
        url = f"https://openlibrary.org/search.json?q={query}&limit=1"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('docs') and len(data['docs']) > 0:
                doc = data['docs'][0]
                isbns = doc.get('isbn', [])
                isbn_13 = [isbn for isbn in isbns if len(isbn) == 13]
                isbn_10 = [isbn for isbn in isbns if len(isbn) == 10]
                return {
                    'title': doc.get('title'),
                    'isbn_13': isbn_13[0] if isbn_13 else None,
                    'isbn_10': isbn_10[0] if isbn_10 else None,
                    'all_isbns': isbns[:5]  # 前5个 ISBN
                }
    except Exception as e:
        print(f"Error: {e}")
    return None

# 需要修正的图书
books_to_fix = [
    {'title': 'Orbital', 'author': 'Samantha Harvey', 'current_isbn': '9780802163807'},
    {'title': 'Prophet Song', 'author': 'Paul Lynch', 'current_isbn': '9780802161513'},
]

print("搜索正确的 ISBN...\n")

for book in books_to_fix:
    print(f"📚 {book['title']} by {book['author']}")
    print(f"   当前 ISBN: {book['current_isbn']}")
    
    result = search_openlib(book['title'], book['author'])
    if result:
        print(f"   找到 ISBN-13: {result['isbn_13']}")
        print(f"   找到 ISBN-10: {result['isbn_10']}")
        print(f"   所有 ISBN: {result['all_isbns']}")
    else:
        print("   ❌ 未找到")
    print()
