#!/usr/bin/env python3
"""
查询获奖图书的不同版本ISBN（精装版和平装版）
使用 Google Books API 和 Open Library API
"""

import requests
import time
from app import create_app
from app.models.schemas import AwardBook

app = create_app()

def search_google_books_editions(title, author, api_key):
    """搜索 Google Books API 获取不同版本的ISBN"""
    try:
        query = f"intitle:{title} inauthor:{author}"
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=10&key={api_key}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            editions = []
            if data.get('items'):
                for item in data['items'][:5]:  # 只取前5个结果
                    volume_info = item.get('volumeInfo', {})
                    identifiers = volume_info.get('industryIdentifiers', [])
                    
                    isbn_13 = None
                    isbn_10 = None
                    for identifier in identifiers:
                        if identifier.get('type') == 'ISBN_13':
                            isbn_13 = identifier.get('identifier')
                        elif identifier.get('type') == 'ISBN_10':
                            isbn_10 = identifier.get('identifier')
                    
                    # 获取版本信息
                    edition = 'Unknown'
                    categories = volume_info.get('categories', [])
                    description = volume_info.get('description', '').lower()
                    
                    # 通过描述或类别判断版本类型
                    if any('hardcover' in cat.lower() or 'hardback' in cat.lower() for cat in categories):
                        edition = 'Hardcover'
                    elif any('paperback' in cat.lower() or 'softcover' in cat.lower() for cat in categories):
                        edition = 'Paperback'
                    elif 'hardcover' in description or 'hardback' in description:
                        edition = 'Hardcover'
                    elif 'paperback' in description or 'softcover' in description:
                        edition = 'Paperback'
                    
                    if isbn_13:
                        editions.append({
                            'isbn_13': isbn_13,
                            'isbn_10': isbn_10,
                            'edition': edition,
                            'publisher': volume_info.get('publisher', 'Unknown'),
                            'published_date': volume_info.get('publishedDate', 'Unknown')
                        })
            return editions
        elif response.status_code == 429:
            return {'error': 'API限流'}
    except Exception as e:
        return {'error': str(e)}
    return []

def search_openlibrary_editions(isbn):
    """使用 Open Library API 获取版本信息"""
    try:
        url = f"https://openlibrary.org/isbn/{isbn}.json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # 获取作品ID
            works = data.get('works', [])
            if works:
                work_id = works[0].get('key', '').split('/')[-1]
                # 查询作品的所有版本
                editions_url = f"https://openlibrary.org/works/{work_id}/editions.json"
                editions_response = requests.get(editions_url, timeout=10)
                if editions_response.status_code == 200:
                    editions_data = editions_response.json()
                    editions = []
                    for entry in editions_data.get('entries', [])[:10]:
                        isbns = entry.get('isbn_13', [])
                        isbn_10s = entry.get('isbn_10', [])
                        physical_format = entry.get('physical_format', 'Unknown')
                        
                        if isbns:
                            editions.append({
                                'isbn_13': isbns[0],
                                'isbn_10': isbn_10s[0] if isbn_10s else None,
                                'edition': physical_format,
                                'publisher': entry.get('publishers', ['Unknown'])[0] if entry.get('publishers') else 'Unknown',
                                'published_date': entry.get('publish_date', 'Unknown')
                            })
                    return editions
        return []
    except Exception as e:
        return {'error': str(e)}

# 从配置文件读取 API Key
from app.config import Config
api_key = Config.GOOGLE_API_KEY

print("="*100)
print("查询获奖图书的不同版本 ISBN（精装版/平装版）")
print("="*100)

with app.app_context():
    books = AwardBook.query.all()
    
    for i, book in enumerate(books, 1):
        print(f"\n[{i}/{len(books)}] 📚 {book.title}")
        print(f"   作者: {book.author}")
        print(f"   当前 ISBN: {book.isbn13}")
        print(f"   奖项: {book.award.name if book.award else 'Unknown'} ({book.year})")
        
        if not book.isbn13:
            print("   ❌ 无 ISBN，跳过")
            continue
        
        # 使用 Open Library 查询版本信息
        print("   🔍 查询 Open Library...")
        editions = search_openlibrary_editions(book.isbn13)
        
        if isinstance(editions, dict) and 'error' in editions:
            print(f"   ❌ 错误: {editions['error']}")
        elif editions:
            print(f"   ✅ 找到 {len(editions)} 个版本:")
            for edition in editions:
                edition_type = edition.get('edition', 'Unknown')
                if edition_type == 'Unknown':
                    edition_type = '未指定'
                elif edition_type.lower() in ['hardcover', 'hardback']:
                    edition_type = '精装版'
                elif edition_type.lower() in ['paperback', 'softcover']:
                    edition_type = '平装版'
                
                print(f"      - {edition_type}")
                print(f"        ISBN-13: {edition.get('isbn_13', 'N/A')}")
                print(f"        ISBN-10: {edition.get('isbn_10', 'N/A')}")
                print(f"        出版社: {edition.get('publisher', 'N/A')}")
                print(f"        出版日期: {edition.get('published_date', 'N/A')}")
        else:
            print("   ⚠️ 未找到版本信息")
        
        # 添加延迟避免请求过快
        time.sleep(0.5)
        
        # 每5本书暂停一下
        if i % 5 == 0:
            print("\n   ⏸️  暂停2秒...")
            time.sleep(2)

print("\n" + "="*100)
print("查询完成")
print("="*100)
