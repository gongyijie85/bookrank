#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试API接口"""

import urllib.request
import urllib.error
import json

def test_api(endpoint, port=8080, timeout=60):
    url = f'http://127.0.0.1:{port}{endpoint}'
    try:
        print(f"\n测试 API: {url}")
        response = urllib.request.urlopen(url, timeout=timeout)
        print(f"状态码: {response.status}")
        content = response.read()
        try:
            data = json.loads(content)
            # 只显示图书数量而不是完整内容
            if 'data' in data and 'books' in data['data']:
                books_summary = {}
                for cat, books in data['data']['books'].items():
                    books_summary[cat] = len(books)
                print(f"图书数量: {books_summary}")
            else:
                print(f"响应: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}...")
        except:
            print(f"响应: {content[:500]}...")
        return True
    except urllib.error.HTTPError as e:
        print(f"HTTP错误: {e.code} - {e.reason}")
        print(f"响应内容: {e.read().decode()[:500]}")
        return False
    except Exception as e:
        print(f"错误: {type(e).__name__}: {e}")
        return False

if __name__ == '__main__':
    # 测试健康检查
    test_api('/api/health', timeout=10)
    
    # 测试获取图书（使用较长的超时时间）
    print("\n正在获取图书数据，这可能需要一些时间...")
    test_api('/api/books/all?session_id=test123', timeout=60)
    
    print("\n" + "="*50)
    print("API测试完成")
