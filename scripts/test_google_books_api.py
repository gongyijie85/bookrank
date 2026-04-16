"""
测试Google Books API响应

直接测试Google Books API的响应，验证查询参数是否正确。
"""
import requests
import json

# 测试不同的查询参数
test_queries = [
    # 原始查询 - 带publishedDate参数
    'subject:fiction+publishedDate:2024:2026',
    # 简化查询 - 不带日期范围
    'subject:fiction',
    # 另一种日期格式
    'subject:fiction+after:2023-12-31',
    # 直接搜索2024年的书
    'publishedDate:2024'
]

base_url = 'https://www.googleapis.com/books/v1/volumes'

for i, query in enumerate(test_queries):
    print(f"\n=== 测试查询 {i+1} ===")
    print(f"查询参数: {query}")
    
    params = {
        'q': query,
        'maxResults': 10,
        'printType': 'books',
        'langRestrict': 'en'
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print(f"状态码: {response.status_code}")
        print(f"总结果数: {data.get('totalItems', 0)}")
        
        items = data.get('items', [])
        print(f"返回书籍数: {len(items)}")
        
        # 显示前3本书的信息
        for j, item in enumerate(items[:3]):
            volume_info = item.get('volumeInfo', {})
            title = volume_info.get('title', '未知标题')
            authors = volume_info.get('authors', ['未知作者'])
            published_date = volume_info.get('publishedDate', '未知日期')
            
            print(f"  {j+1}. {title}")
            print(f"     作者: {', '.join(authors)}")
            print(f"     出版日期: {published_date}")
            
    except Exception as e:
        print(f"错误: {e}")
