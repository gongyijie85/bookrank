#!/usr/bin/env python3
"""
使用 Google Books API 搜索正确的 ISBN
"""

import requests
import time

def search_google_books(title, author, api_key):
    """搜索 Google Books API"""
    try:
        query = f"intitle:{title} inauthor:{author}"
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=1&key={api_key}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('items') and len(data['items']) > 0:
                item = data['items'][0]
                volume_info = item.get('volumeInfo', {})
                identifiers = volume_info.get('industryIdentifiers', [])
                
                isbn_13 = None
                isbn_10 = None
                for identifier in identifiers:
                    if identifier.get('type') == 'ISBN_13':
                        isbn_13 = identifier.get('identifier')
                    elif identifier.get('type') == 'ISBN_10':
                        isbn_10 = identifier.get('identifier')
                
                return {
                    'title': volume_info.get('title'),
                    'isbn_13': isbn_13,
                    'isbn_10': isbn_10,
                    'published_date': volume_info.get('publishedDate'),
                    'publisher': volume_info.get('publisher')
                }
        elif response.status_code == 429:
            return {'error': 'API限流，请稍后再试'}
    except Exception as e:
        return {'error': str(e)}
    return None

# 从配置文件读取 API Key
import os
import sys
sys.path.insert(0, 'd:\\BookRank3')
from app.config import Config

api_key = Config.GOOGLE_API_KEY

# 需要修正的图书
books_to_fix = [
    {'title': 'Orbital', 'author': 'Samantha Harvey', 'current_isbn': '9780802163807'},
    {'title': 'Prophet Song', 'author': 'Paul Lynch', 'current_isbn': '9780802161513'},
]

print("使用 Google Books API 搜索正确的 ISBN...\n")

for book in books_to_fix:
    print(f"📚 {book['title']} by {book['author']}")
    print(f"   当前 ISBN: {book['current_isbn']}")
    
    result = search_google_books(book['title'], book['author'], api_key)
    if result:
        if 'error' in result:
            print(f"   ❌ {result['error']}")
        else:
            print(f"   ✅ 找到图书: {result['title']}")
            print(f"   ISBN-13: {result['isbn_13']}")
            print(f"   ISBN-10: {result['isbn_10']}")
            print(f"   出版日期: {result['published_date']}")
            print(f"   出版社: {result['publisher']}")
    else:
        print("   ❌ 未找到")
    print()
    
    time.sleep(1)  # 避免请求过快
