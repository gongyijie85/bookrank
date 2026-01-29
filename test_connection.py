#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试连接脚本"""

import urllib.request
import urllib.error

def test_connection(port=8080):
    url = f'http://127.0.0.1:{port}/'
    try:
        print(f"正在测试连接到 {url}...")
        response = urllib.request.urlopen(url, timeout=10)
        print(f"状态码: {response.status}")
        print(f"响应头: {dict(response.headers)}")
        content = response.read()[:500]
        print(f"响应内容前500字节: {content}")
        return True
    except urllib.error.HTTPError as e:
        print(f"HTTP错误: {e.code} - {e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f"URL错误: {e.reason}")
        return False
    except Exception as e:
        print(f"其他错误: {type(e).__name__}: {e}")
        return False

if __name__ == '__main__':
    success = test_connection(8080)
    print(f"\n连接测试{'成功' if success else '失败'}")
