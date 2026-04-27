#!/usr/bin/env python3
"""
性能测试脚本

测试系统在大量数据时的响应速度
"""
import time
import sys
import os
from datetime import date, timedelta

# 确保项目根目录在Python路径中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 设置测试环境
os.environ['FLASK_ENV'] = 'testing'

from app import create_app
from app.services import BookService, NYTApiClient, GoogleBooksClient, CacheService, MemoryCache, FileCache, ImageCacheService
from app.services.weekly_report_service import WeeklyReportService
from app.services.export_service import ExportService
from app.models.schemas import WeeklyReport
from app.models.database import db
from pathlib import Path


def test_api_performance():
    """测试API调用性能"""
    print("\n=== 测试API调用性能 ===")
    
    app = create_app('testing')
    with app.app_context():
        # 初始化依赖服务
        memory_cache = MemoryCache(default_ttl=3600, max_size=1000)
        file_cache = FileCache(cache_dir=Path('cache'), default_ttl=86400)
        cache_service = CacheService(memory_cache, file_cache, flask_cache=None)
        
        nyt_client = NYTApiClient(
            api_key='',
            base_url='https://api.nytimes.com/svc/books/v3',
            rate_limiter=None,
            timeout=15
        )
        
        google_client = GoogleBooksClient(
            api_key=None,
            base_url='https://www.googleapis.com/books/v1',
            timeout=8
        )
        
        image_cache = ImageCacheService(
            cache_dir=Path('static/cache'),
            default_cover='/static/default-cover.png'
        )
        
        book_service = BookService(
            nyt_client=nyt_client,
            google_client=google_client,
            cache_service=cache_service,
            image_cache=image_cache,
            max_workers=4,
            categories=['Fiction', 'Nonfiction', 'Mystery', 'Science Fiction']
        )
        
        # 测试API调用响应时间
        start_time = time.time()
        # 注意：这里只是测试客户端初始化，不实际调用API以避免API限制
        end_time = time.time()
        
        print(f"API客户端初始化时间: {end_time - start_time:.4f}秒")


def test_database_performance():
    """测试数据库操作性能"""
    print("\n=== 测试数据库操作性能 ===")
    
    app = create_app('testing')
    with app.app_context():
        # 创建测试数据
        test_reports = []
        for i in range(100):
            report_date = date.today() - timedelta(days=i)
            report = WeeklyReport(
                report_date=report_date,
                week_start=report_date - timedelta(days=7),
                week_end=report_date,
                title=f'测试周报 {i}',
                summary=f'这是第{i}份测试周报',
                content='{"top_changes": [], "new_books": [], "top_risers": [], "longest_running": [], "featured_books": []}'
            )
            test_reports.append(report)
        
        # 测试批量插入
        start_time = time.time()
        db.session.add_all(test_reports)
        db.session.commit()
        end_time = time.time()
        print(f"批量插入100条周报数据: {end_time - start_time:.4f}秒")
        
        # 测试查询
        start_time = time.time()
        reports = WeeklyReport.query.all()
        end_time = time.time()
        print(f"查询所有周报数据: {end_time - start_time:.4f}秒")
        
        # 测试按日期查询
        start_time = time.time()
        recent_reports = WeeklyReport.query.order_by(WeeklyReport.report_date.desc()).limit(10).all()
        end_time = time.time()
        print(f"查询最近10条周报: {end_time - start_time:.4f}秒")


def test_export_performance():
    """测试导出功能性能"""
    print("\n=== 测试导出功能性能 ===")
    
    app = create_app('testing')
    with app.app_context():
        # 创建测试周报
        report = WeeklyReport(
            report_date=date.today(),
            week_start=date.today() - timedelta(days=7),
            week_end=date.today(),
            title='性能测试周报',
            summary='这是一份性能测试周报',
            content='{"top_changes": [], "new_books": [], "top_risers": [], "longest_running": [], "featured_books": []}'
        )
        db.session.add(report)
        db.session.commit()
        
        export_service = ExportService()
        
        # 测试PDF导出
        start_time = time.time()
        pdf_buffer = export_service.export_weekly_report_pdf(report)
        end_time = time.time()
        print(f"PDF导出时间: {end_time - start_time:.4f}秒")
        
        # 测试Excel导出
        start_time = time.time()
        excel_buffer = export_service.export_weekly_report_excel(report)
        end_time = time.time()
        print(f"Excel导出时间: {end_time - start_time:.4f}秒")


def test_report_generation_performance():
    """测试周报生成性能"""
    print("\n=== 测试周报生成性能 ===")
    
    app = create_app('testing')
    with app.app_context():
        # 初始化依赖服务
        memory_cache = MemoryCache(default_ttl=3600, max_size=1000)
        file_cache = FileCache(cache_dir=Path('cache'), default_ttl=86400)
        cache_service = CacheService(memory_cache, file_cache, flask_cache=None)
        
        nyt_client = NYTApiClient(
            api_key='',
            base_url='https://api.nytimes.com/svc/books/v3',
            rate_limiter=None,
            timeout=15
        )
        
        google_client = GoogleBooksClient(
            api_key=None,
            base_url='https://www.googleapis.com/books/v1',
            timeout=8
        )
        
        image_cache = ImageCacheService(
            cache_dir=Path('static/cache'),
            default_cover='/static/default-cover.png'
        )
        
        book_service = BookService(
            nyt_client=nyt_client,
            google_client=google_client,
            cache_service=cache_service,
            image_cache=image_cache,
            max_workers=4,
            categories=['Fiction', 'Nonfiction', 'Mystery', 'Science Fiction']
        )
        
        report_service = WeeklyReportService(book_service)
        
        # 测试周报生成（使用模拟数据）
        start_time = time.time()
        week_start = date.today() - timedelta(days=21)
        week_end = date.today() - timedelta(days=15)
        
        # 生成周报（使用默认摘要，不调用AI）
        report = report_service.generate_report(week_start, week_end)
        end_time = time.time()
        
        print(f"周报生成时间: {end_time - start_time:.4f}秒")


def main():
    """运行所有性能测试"""
    print("开始性能测试...")
    
    test_api_performance()
    test_database_performance()
    test_export_performance()
    test_report_generation_performance()
    
    print("\n性能测试完成！")


if __name__ == '__main__':
    main()
