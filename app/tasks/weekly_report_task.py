"""周报定时任务"""
import datetime
import logging
from typing import Optional

from ..models.schemas import WeeklyReport
from ..services.weekly_report_service import WeeklyReportService

logger = logging.getLogger(__name__)


def generate_weekly_report() -> Optional[WeeklyReport]:
    """生成周报"""
    try:
        # 计算上周的开始和结束日期
        today = datetime.date.today()
        # 上周日作为周结束
        last_sunday = today - datetime.timedelta(days=today.weekday() + 1)
        # 上周一作为周开始
        last_monday = last_sunday - datetime.timedelta(days=6)
        
        # 检查是否已经生成过该周的报告
        existing_report = WeeklyReport.query.filter(
            WeeklyReport.week_start == last_monday,
            WeeklyReport.week_end == last_sunday
        ).first()
        
        if existing_report:
            logger.info(f"周报已存在: {last_monday} 至 {last_sunday}")
            # 发送邮件
            send_weekly_report_email(existing_report)
            return existing_report
        
        # 初始化服务
        from ..services import (
            BookService, NYTApiClient, GoogleBooksClient, 
            CacheService, MemoryCache, FileCache, ImageCacheService
        )

        # 初始化依赖服务
        from pathlib import Path
        
        memory_cache = MemoryCache(default_ttl=3600, max_size=1000)
        file_cache = FileCache(cache_dir=Path('cache'), default_ttl=86400)
        cache_service = CacheService(memory_cache, file_cache, flask_cache=None)
        
        nyt_client = NYTApiClient(
            api_key='',  # 使用环境变量中的 API 密钥
            base_url='https://api.nytimes.com/svc/books/v3',
            rate_limiter=None,
            timeout=15
        )
        
        google_client = GoogleBooksClient(
            api_key=None,  # 使用环境变量中的 API 密钥
            base_url='https://www.googleapis.com/books/v1',
            timeout=8
        )
        
        image_cache = ImageCacheService(
            cache_dir=Path('static/cache'),
            default_cover='/static/default-cover.png'
        )
        
        # 初始化图书服务
        book_service = BookService(
            nyt_client=nyt_client,
            google_client=google_client,
            cache_service=cache_service,
            image_cache=image_cache,
            max_workers=4,
            categories=['Fiction', 'Nonfiction', 'Mystery', 'Science Fiction']
        )
        
        report_service = WeeklyReportService(book_service)
        
        # 生成报告
        report = report_service.generate_report(last_monday, last_sunday)
        
        if report:
            logger.info(f"周报生成成功: {report.title}")
            # 发送邮件
            send_weekly_report_email(report)
            return report
        else:
            logger.error("周报生成失败")
            return None
            
    except Exception as e:
        logger.error(f"生成周报时出错: {str(e)}")
        return None

def send_weekly_report_email(report: WeeklyReport) -> bool:
    """发送周报邮件
    
    Args:
        report: 周报对象
        
    Returns:
        bool: 是否发送成功
    """
    try:
        from flask import current_app
        
        # 检查邮件配置
        if not current_app.config.get('MAIL_USERNAME') or not current_app.config.get('MAIL_PASSWORD'):
            logger.warning("邮件服务未配置，跳过邮件发送")
            return False
        
        # 初始化邮件服务
        from flask_mail import Mail
        from ..services.email_service import EmailService
        
        mail = current_app.extensions.get('mail')
        if not mail:
            mail = Mail(current_app)
            current_app.extensions['mail'] = mail
        
        email_service = EmailService(mail)
        
        # 收件人列表（可以从配置或数据库中获取）
        recipients = current_app.config.get('MAIL_RECIPIENTS', '').split(',') if current_app.config.get('MAIL_RECIPIENTS') else []
        
        # 如果没有配置收件人，使用默认收件人
        if not recipients:
            recipients = [current_app.config.get('MAIL_DEFAULT_SENDER')]
        
        # 过滤空邮箱
        recipients = [email.strip() for email in recipients if email.strip()]
        
        if not recipients:
            logger.warning("未配置收件人，跳过邮件发送")
            return False
        
        # 发送邮件
        return email_service.send_weekly_report_email(report, recipients)
        
    except Exception as e:
        logger.error(f"发送周报邮件时出错: {str(e)}")
        return False

def schedule_weekly_report():
    """调度周报生成任务"""
    # 这里可以使用任务调度器，如APScheduler
    # 例如：每天检查是否需要生成周报
    report = generate_weekly_report()
    return report
