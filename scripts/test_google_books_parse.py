"""
测试Google Books API响应和解析逻辑

直接测试API响应并验证解析逻辑是否正确。
"""
import requests
import json
from datetime import datetime

# 测试API响应
url = 'https://www.googleapis.com/books/v1/volumes'
params = {
    'q': 'publishedDate:2024',
    'maxResults': 5,
    'printType': 'books',
    'langRestrict': 'en'
}

print("=== 测试Google Books API响应 ===")
try:
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    
    print(f"状态码: {response.status_code}")
    print(f"总结果数: {data.get('totalItems', 0)}")
    
    items = data.get('items', [])
    print(f"返回书籍数: {len(items)}")
    
    # 模拟解析逻辑
    print("\n=== 测试解析逻辑 ===")
    for i, item in enumerate(items):
        volume_info = item.get('volumeInfo', {})
        
        # 模拟_parse_volume_info方法的逻辑
        title = volume_info.get('title', '')
        if not title:
            print(f"❌ 跳过: 无标题")
            continue
        
        authors = volume_info.get('authors', ['Unknown Author'])
        author = authors[0] if authors else 'Unknown Author'
        
        published_date = volume_info.get('publishedDate', '')
        publication_date = None
        if published_date:
            try:
                if len(published_date) >= 10:
                    publication_date = datetime.strptime(published_date[:10], '%Y-%m-%d').date()
                elif len(published_date) >= 4:
                    publication_date = datetime.strptime(published_date[:4], '%Y').date()
            except ValueError as e:
                print(f"❌ 日期解析失败: {e}")
        
        print(f"\n{i+1}. {title}")
        print(f"   作者: {author}")
        print(f"   原始出版日期: {published_date}")
        print(f"   解析后日期: {publication_date}")
        
        # 测试ISBN解析
        industry_identifiers = volume_info.get('industryIdentifiers', [])
        isbn_13 = None
        isbn_10 = None
        for identifier in industry_identifiers:
            if identifier.get('type') == 'ISBN_13':
                isbn_13 = identifier.get('identifier')
            elif identifier.get('type') == 'ISBN_10':
                isbn_10 = identifier.get('identifier')
        
        print(f"   ISBN-13: {isbn_13}")
        print(f"   ISBN-10: {isbn_10}")
        
        # 测试封面URL
        image_links = volume_info.get('imageLinks', {})
        cover_url = None
        if image_links:
            cover_url = image_links.get('thumbnail') or image_links.get('smallThumbnail')
            if cover_url and cover_url.startswith('http'):
                cover_url = cover_url.replace('http://', 'https://')
        print(f"   封面URL: {cover_url}")
        
        # 测试描述
        description = volume_info.get('description')
        if description:
            print(f"   描述: {description[:100]}...")
        else:
            print(f"   描述: 无")
            
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
