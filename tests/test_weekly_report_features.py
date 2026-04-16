"""测试周报相关功能"""
import pytest
from datetime import date, timedelta
from io import BytesIO


class TestEmailService:
    """测试邮件服务"""
    
    def test_email_service_init(self, app):
        """测试邮件服务初始化"""
        with app.app_context():
            from app.services.email_service import EmailService
            from flask_mail import Mail
            
            mail = Mail(app)
            email_service = EmailService(mail)
            assert email_service is not None
    
    def test_is_email_configured(self, app):
        """测试邮件配置检查"""
        with app.app_context():
            from app.services.email_service import EmailService
            from flask_mail import Mail
            
            mail = Mail(app)
            email_service = EmailService(mail)
            # 测试环境下邮件配置不完整
            assert not email_service.is_email_configured()
    
    def test_send_test_email(self, app):
        """测试发送测试邮件"""
        with app.app_context():
            from app.services.email_service import EmailService
            from flask_mail import Mail
            
            mail = Mail(app)
            email_service = EmailService(mail)
            # 测试环境下邮件发送应该失败
            result = email_service.send_test_email('test@example.com')
            assert not result


class TestExportService:
    """测试导出服务"""
    
    def test_export_service_init(self):
        """测试导出服务初始化"""
        from app.services.export_service import ExportService
        export_service = ExportService()
        assert export_service is not None
    
    def test_export_pdf(self, app, db):
        """测试PDF导出"""
        with app.app_context():
            from app.services.export_service import ExportService
            from app.models.schemas import WeeklyReport
            
            # 创建测试周报
            report = WeeklyReport(
                report_date=date.today(),
                week_start=date.today() - timedelta(days=7),
                week_end=date.today(),
                title='测试周报',
                summary='这是一份测试周报',
                content='{"top_changes": [], "new_books": [], "top_risers": [], "longest_running": [], "featured_books": []}'
            )
            db.session.add(report)
            db.session.commit()
            
            # 测试PDF导出
            export_service = ExportService()
            pdf_buffer = export_service.export_weekly_report_pdf(report)
            assert pdf_buffer is not None
            assert isinstance(pdf_buffer, BytesIO)
    
    def test_export_excel(self, app, db):
        """测试Excel导出"""
        with app.app_context():
            from app.services.export_service import ExportService
            from app.models.schemas import WeeklyReport
            
            # 创建测试周报
            report = WeeklyReport(
                report_date=date.today(),
                week_start=date.today() - timedelta(days=7),
                week_end=date.today(),
                title='测试周报',
                summary='这是一份测试周报',
                content='{"top_changes": [], "new_books": [], "top_risers": [], "longest_running": [], "featured_books": []}'
            )
            db.session.add(report)
            db.session.commit()
            
            # 测试Excel导出
            export_service = ExportService()
            excel_buffer = export_service.export_weekly_report_excel(report)
            assert excel_buffer is not None
            assert isinstance(excel_buffer, BytesIO)


class TestWeeklyReportService:
    """测试周报服务"""
    
    def test_weekly_report_service_init(self, app):
        """测试周报服务初始化"""
        with app.app_context():
            from app.services.weekly_report_service import WeeklyReportService
            from app.services import BookService, NYTApiClient, GoogleBooksClient, CacheService, MemoryCache, FileCache, ImageCacheService
            from pathlib import Path
            
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
            assert report_service is not None
    
    def test_generate_report(self, app, db):
        """测试生成周报"""
        with app.app_context():
            # 先创建测试数据
            from app.models.schemas import Award, AwardBook
            award = Award(name='测试奖项', name_en='Test Award', country='US', category_count=1)
            db.session.add(award)
            db.session.flush()
            for i in range(5):
                book = AwardBook(
                    award_id=award.id, year=2026, category='Fiction',
                    rank=i + 1, title=f'Test Book {i+1}', author=f'Author {i+1}',
                    is_displayable=True
                )
                db.session.add(book)
            db.session.commit()

            from app.services.weekly_report_service import WeeklyReportService
            from app.services import BookService, NYTApiClient, GoogleBooksClient, CacheService, MemoryCache, FileCache, ImageCacheService
            from pathlib import Path
            
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
            
            # 测试生成周报
            week_start = date.today() - timedelta(days=21)
            week_end = date.today() - timedelta(days=15)
            
            report = report_service.generate_report(week_start, week_end)
            assert report is not None
            assert report.title is not None
            assert report.summary is not None
    
    def test_get_reports(self, app):
        """测试获取周报列表"""
        with app.app_context():
            from app.services.weekly_report_service import WeeklyReportService
            from app.services import BookService, NYTApiClient, GoogleBooksClient, CacheService, MemoryCache, FileCache, ImageCacheService
            from pathlib import Path
            
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
            
            # 测试获取周报列表
            reports = report_service.get_reports()
            assert isinstance(reports, list)


class TestWeeklyReportRoutes:
    """测试周报相关路由"""
    
    def test_weekly_reports_route(self, client):
        """测试周报列表路由"""
        response = client.get('/reports/weekly')
        assert response.status_code == 200
        assert '畅销书周报'.encode('utf-8') in response.data
    
    def test_weekly_report_detail_route(self, client, app, db):
        """测试周报详情路由"""
        with app.app_context():
            from app.models.schemas import WeeklyReport
            
            # 创建测试周报
            report = WeeklyReport(
                report_date=date.today(),
                week_start=date.today() - timedelta(days=7),
                week_end=date.today(),
                title='测试周报',
                summary='这是一份测试周报',
                content='{"top_changes": [], "new_books": [], "top_risers": [], "longest_running": [], "featured_books": []}'
            )
            db.session.add(report)
            db.session.commit()
            
            # 测试详情路由
            date_str = report.report_date.strftime('%Y-%m-%d')
            response = client.get(f'/reports/weekly/{date_str}')
            assert response.status_code == 200
            assert '测试周报'.encode('utf-8') in response.data
    
    def test_export_route(self, client, app, db):
        """测试导出路由"""
        with app.app_context():
            from app.models.schemas import WeeklyReport
            
            # 创建测试周报
            report = WeeklyReport(
                report_date=date.today(),
                week_start=date.today() - timedelta(days=7),
                week_end=date.today(),
                title='测试周报',
                summary='这是一份测试周报',
                content='{"top_changes": [], "new_books": [], "top_risers": [], "longest_running": [], "featured_books": []}'
            )
            db.session.add(report)
            db.session.commit()
            
            # 测试PDF导出
            date_str = report.report_date.strftime('%Y-%m-%d')
            response = client.get(f'/reports/weekly/{date_str}/export?format=pdf')
            assert response.status_code == 200
            assert response.content_type == 'application/pdf'
            
            # 测试Excel导出
            response = client.get(f'/reports/weekly/{date_str}/export?format=excel')
            assert response.status_code == 200
            assert response.content_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
