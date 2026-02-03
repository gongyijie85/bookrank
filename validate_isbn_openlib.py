#!/usr/bin/env python3
"""
使用 Open Library API 验证 ISBN
"""

import requests
import time

# 获奖图书数据
sample_books = [
    {'award_name': '普利策奖', 'year': 2025, 'title': 'James', 'author': 'Percival Everett', 'isbn13': '9780385550369'},
    {'award_name': '普利策奖', 'year': 2024, 'title': 'The Nickel Boys', 'author': 'Colson Whitehead', 'isbn13': '9780385537070'},
    {'award_name': '普利策奖', 'year': 2023, 'title': 'Demon Copperhead', 'author': 'Barbara Kingsolver', 'isbn13': '9780063251922'},
    {'award_name': '布克奖', 'year': 2024, 'title': 'Orbital', 'author': 'Samantha Harvey', 'isbn13': '9780802163807'},
    {'award_name': '布克奖', 'year': 2023, 'title': 'Prophet Song', 'author': 'Paul Lynch', 'isbn13': '9780802161513'},
    {'award_name': '诺贝尔文学奖', 'year': 2024, 'title': 'The Vegetarian', 'author': 'Han Kang', 'isbn13': '9780553448184'},
    {'award_name': '雨果奖', 'year': 2025, 'title': 'The Tainted Cup', 'author': 'Robert Jackson Bennett', 'isbn13': '9781984820709'},
    {'award_name': '星云奖', 'year': 2023, 'title': 'Babel: Or the Necessity of Violence', 'author': 'R.F. Kuang', 'isbn13': '9780063021426'},
]

def check_isbn_openlib(isbn):
    """使用 Open Library API 检查 ISBN"""
    try:
        url = f"https://openlibrary.org/isbn/{isbn}.json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'found': True,
                'title': data.get('title', 'Unknown'),
                'authors': data.get('authors', []),
                'publish_date': data.get('publish_date', 'Unknown')
            }
        return {'found': False}
    except Exception as e:
        return {'found': False, 'error': str(e)}

def search_by_title_openlib(title, author):
    """使用 Open Library API 搜索书名"""
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
                return {
                    'found': True,
                    'title': doc.get('title', 'Unknown'),
                    'isbn_13': isbn_13[0] if isbn_13 else None,
                    'isbn_10': [isbn for isbn in isbns if len(isbn) == 10][0] if [isbn for isbn in isbns if len(isbn) == 10] else None
                }
        return {'found': False}
    except Exception as e:
        return {'found': False, 'error': str(e)}

print("="*80)
print("使用 Open Library API 验证 ISBN")
print("="*80)

corrections = []

for i, book in enumerate(sample_books, 1):
    print(f"\n[{i}/{len(sample_books)}] {book['award_name']} ({book['year']})")
    print(f"   书名: {book['title']}")
    print(f"   作者: {book['author']}")
    print(f"   当前 ISBN: {book['isbn13']}")
    
    # 使用 ISBN 查询
    result = check_isbn_openlib(book['isbn13'])
    if result['found']:
        print(f"   ✅ ISBN 有效: {result['title']}")
    else:
        print(f"   ❌ ISBN 无效，尝试用书名搜索...")
        # 使用书名搜索
        search_result = search_by_title_openlib(book['title'], book['author'])
        if search_result['found']:
            print(f"   ✅ 找到图书: {search_result['title']}")
            if search_result['isbn_13'] and search_result['isbn_13'] != book['isbn13']:
                print(f"   ⚠️ ISBN 不匹配!")
                print(f"      当前: {book['isbn13']}")
                print(f"      建议: {search_result['isbn_13']}")
                corrections.append({
                    'title': book['title'],
                    'old_isbn': book['isbn13'],
                    'new_isbn': search_result['isbn_13']
                })
            elif search_result['isbn_13']:
                print(f"   ✅ ISBN 正确")
        else:
            print(f"   ❌ 书名搜索也失败")
    
    time.sleep(0.5)  # 避免请求过快

print("\n" + "="*80)
print("验证完成")
print("="*80)

if corrections:
    print(f"\n发现 {len(corrections)} 个需要修正的 ISBN:")
    for item in corrections:
        print(f"  - {item['title']}")
        print(f"    {item['old_isbn']} -> {item['new_isbn']}")
else:
    print("\n✅ 所有 ISBN 都正确")
