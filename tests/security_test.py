#!/usr/bin/env python3
"""
安全测试脚本

测试系统的安全性，包括输入验证、XSS、SQL注入、敏感信息泄露等
"""
import sys
import os
import re

# 确保项目根目录在Python路径中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 设置测试环境
os.environ['FLASK_ENV'] = 'testing'

from app import create_app


def test_input_validation():
    """测试输入验证"""
    print("\n=== 测试输入验证 ===")
    
    app = create_app('testing')
    client = app.test_client()
    
    # 测试导出路由的格式参数验证
    response = client.get('/reports/weekly/2024-01-01/export?format=invalid')
    print(f"无效格式参数响应: {response.status_code}")
    
    # 测试日期参数验证
    response = client.get('/reports/weekly/invalid-date')
    print(f"无效日期参数响应: {response.status_code}")


def test_xss_protection():
    """测试XSS防护"""
    print("\n=== 测试XSS防护 ===")
    
    app = create_app('testing')
    client = app.test_client()
    
    # 测试可能的XSS攻击
    xss_payload = '<script>alert("XSS")</script>'
    
    # 测试GET请求中的XSS
    response = client.get(f'/reports/weekly/2024-01-01/export?format=pdf&title={xss_payload}')
    print(f"GET请求XSS防护响应: {response.status_code}")
    
    # 检查响应中是否包含XSS payload
    if xss_payload in response.data.decode('utf-8'):
        print("⚠️  XSS防护可能存在问题")
    else:
        print("✅ XSS防护正常")


def test_sql_injection():
    """测试SQL注入防护"""
    print("\n=== 测试SQL注入防护 ===")
    
    app = create_app('testing')
    client = app.test_client()
    
    # 测试SQL注入攻击
    sql_payload = '2024-01-01\' OR 1=1 --'
    response = client.get(f'/reports/weekly/{sql_payload}')
    print(f"SQL注入测试响应: {response.status_code}")
    
    # 检查是否返回异常信息
    if 'error' in response.data.decode('utf-8').lower():
        print("⚠️  可能存在SQL注入风险")
    else:
        print("✅ SQL注入防护正常")


def test_sensitive_info_leakage():
    """测试敏感信息泄露"""
    print("\n=== 测试敏感信息泄露 ===")
    
    app = create_app('testing')
    client = app.test_client()
    
    # 测试错误页面是否泄露敏感信息
    response = client.get('/nonexistent-path')
    print(f"404页面响应: {response.status_code}")
    
    # 检查响应中是否包含敏感信息
    error_page = response.data.decode('utf-8')
    sensitive_patterns = [
        'traceback', 'exception', 'error', 'stack',
        'database', 'password', 'secret', 'api_key'
    ]
    
    for pattern in sensitive_patterns:
        if pattern in error_page.lower():
            print(f"⚠️  可能泄露敏感信息: {pattern}")
    
    # 测试安全响应头
    print("\n测试安全响应头:")
    headers = response.headers
    
    # 检查Content-Security-Policy
    if 'Content-Security-Policy' in headers:
        print("✅ Content-Security-Policy 头存在")
    else:
        print("⚠️  Content-Security-Policy 头缺失")
    
    # 检查X-Content-Type-Options
    if 'X-Content-Type-Options' in headers:
        print("✅ X-Content-Type-Options 头存在")
    else:
        print("⚠️  X-Content-Type-Options 头缺失")
    
    # 检查X-Frame-Options
    if 'X-Frame-Options' in headers:
        print("✅ X-Frame-Options 头存在")
    else:
        print("⚠️  X-Frame-Options 头缺失")


def test_api_rate_limiting():
    """测试API速率限制"""
    print("\n=== 测试API速率限制 ===")
    
    app = create_app('testing')
    client = app.test_client()
    
    # 测试短时间内多次请求
    print("测试短时间内多次请求...")
    status_codes = []
    
    for i in range(10):
        response = client.get('/reports/weekly')
        status_codes.append(response.status_code)
    
    # 检查是否有429状态码（请求过多）
    if 429 in status_codes:
        print("✅ API速率限制正常")
    else:
        print("⚠️  API速率限制可能未启用")


def test_cors_policy():
    """测试CORS策略"""
    print("\n=== 测试CORS策略 ===")
    
    app = create_app('testing')
    client = app.test_client()
    
    # 测试跨域请求
    response = client.get('/reports/weekly', headers={
        'Origin': 'https://example.com'
    })
    
    print(f"CORS测试响应: {response.status_code}")
    
    # 检查CORS头
    if 'Access-Control-Allow-Origin' in response.headers:
        print("✅ CORS策略已配置")
    else:
        print("⚠️  CORS策略可能未配置")


def main():
    """运行所有安全测试"""
    print("开始安全测试...")
    
    test_input_validation()
    test_xss_protection()
    test_sql_injection()
    test_sensitive_info_leakage()
    test_api_rate_limiting()
    test_cors_policy()
    
    print("\n安全测试完成！")


if __name__ == '__main__':
    main()
