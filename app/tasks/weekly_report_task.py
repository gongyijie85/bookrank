"""周报定时任务"""
import datetime
import logging
from typing import Optional

from ..models.schemas import WeeklyReport
from ..services.weekly_report_service import WeeklyReportService

logger = logging.getLogger(__name__)


def generate_weekly_report(force_regenerate: bool = False) -> Optional[WeeklyReport]:
    """生成周报（排行榜数据刷新后调用）

    不再限制仅在周五生成，而是在数据刷新后自动触发。
    周一/二/三时生成上周周报（排行榜尚未更新），
    周四及以后生成本周周报（排行榜已更新）。
    """
    try:
        today = datetime.date.today()
        # 计算当前周的日期范围（周一至周日）
        current_monday = today - datetime.timedelta(days=today.weekday())

        # NYT 排行榜通常在周三更新（美国时间），中国时间周四可见
        if today.weekday() <= 2:  # 周一/二/三，排行榜尚未更新
            last_monday = current_monday - datetime.timedelta(days=7)
            last_sunday = current_monday - datetime.timedelta(days=1)
            week_start = last_monday
            week_end = last_sunday
        else:
            # 周四及以后，排行榜已更新
            week_start = current_monday
            week_end = current_monday + datetime.timedelta(days=6)

        # 检查是否已经生成过
        existing_report = WeeklyReport.query.filter(
            WeeklyReport.week_start == week_start,
            WeeklyReport.week_end == week_end
        ).first()

        if existing_report and not force_regenerate:
            logger.info(f"周报已存在: {week_start} 至 {week_end}")
            send_weekly_report_email(existing_report)
            return existing_report

        if existing_report and force_regenerate:
            logger.info(f"强制重新生成周报: {week_start} 至 {week_end}")
        
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
        report = report_service.generate_report(week_start, week_end, force_regenerate=force_regenerate)
        
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

def _get_smtp_config() -> dict:
    """从 Flask 配置读取 SMTP 配置"""
    from flask import current_app
    return {
        'server': current_app.config.get('MAIL_SERVER', 'smtp.gmail.com'),
        'port': current_app.config.get('MAIL_PORT', 587),
        'use_tls': current_app.config.get('MAIL_USE_TLS', True),
        'username': current_app.config.get('MAIL_USERNAME'),
        'password': current_app.config.get('MAIL_PASSWORD'),
        'sender': current_app.config.get('MAIL_DEFAULT_SENDER', 'bookrank@example.com'),
        'recipients': [r.strip() for r in current_app.config.get('MAIL_RECIPIENTS', '').split(',') if r.strip()],
    }


def _render_weekly_report_html(report: WeeklyReport) -> str:
    """渲染周报邮件 HTML（不依赖 Jinja2 模板，内联样式确保邮件客户端兼容）"""
    import json
    from datetime import datetime

    # 解析周报内容 JSON
    try:
        content = json.loads(report.content) if report.content else {}
    except json.JSONDecodeError:
        content = {}

    top_changes = content.get('top_changes', [])[:5]
    featured_books = content.get('featured_books', [])[:5]
    new_books = content.get('new_books', [])[:5]
    top_risers = content.get('top_risers', [])[:5]
    longest_running = content.get('longest_running', [])[:5]

    # 构建图书行 HTML（带封面图）
    def book_row(book: dict) -> str:
        cover = book.get('cover', '')
        title = book.get('title', '未知书名')
        author = book.get('author', '')
        category = book.get('category', '')
        rank = book.get('rank', 0)
        rank_change = book.get('rank_change', 0)
        weeks = book.get('weeks_on_list', 0)

        # 排名变化箭头
        if rank_change > 0:
            change_html = f'<span style="color:#38a169;font-weight:500;">↑ {rank_change} 位</span>'
        elif rank_change < 0:
            change_html = f'<span style="color:#e53e3e;font-weight:500;">↓ {abs(rank_change)} 位</span>'
        else:
            change_html = '<span style="color:#718096;font-weight:500;">→ 无变化</span>'

        # 封面图片（按比例缩放，max-width 限制）
        cover_html = ''
        if cover:
            cover_html = (
                f'<img src="{cover}" alt="{title}" '
                f'style="max-width:60px;height:auto;width:auto;max-height:90px;'
                f'border-radius:4px;vertical-align:top;box-shadow:0 1px 3px rgba(0,0,0,0.1);" '
                f'loading="lazy">'
            )
        else:
            cover_html = '<span style="display:inline-block;width:60px;height:90px;background:#f0f0f0;border-radius:4px;text-align:center;line-height:90px;color:#999;font-size:24px;">📖</span>'

        return f'''<tr>
            <td style="padding:12px;border-bottom:1px solid #f0f0f0;text-align:center;vertical-align:top;">{cover_html}</td>
            <td style="padding:12px;border-bottom:1px solid #f0f0f0;vertical-align:top;">
                <div style="font-weight:600;color:#1d1d1f;font-size:15px;margin-bottom:4px;">{title}</div>
                <div style="color:#666;font-size:13px;margin-bottom:4px;">📝 {author}</div>
                <div style="color:#888;font-size:12px;">🏷️ {category} | 📊 排名: {rank} | {change_html} | 📅 {weeks} 周</div>
            </td>
        </tr>'''

    # 构建各区块
    def section_html(title: str, books: list) -> str:
        if not books:
            return ''
        rows = ''.join(book_row(b) for b in books)
        return f'''<div style="margin-bottom:25px;">
            <h2 style="font-size:18px;font-weight:600;color:#4a5568;border-bottom:2px solid #f0f0f0;padding-bottom:8px;margin:0 0 15px;">{title}</h2>
            <table style="width:100%;border-collapse:collapse;">{rows}</table>
        </div>'''

    date_str = report.report_date.strftime('%Y年%m月%d日') if report.report_date else datetime.now().strftime('%Y年%m月%d日')
    week_start = report.week_start.strftime('%m月%d日') if report.week_start else ''
    week_end = report.week_end.strftime('%m月%d日') if report.week_end else ''

    # 摘要处理（去掉 Markdown # 符号）
    summary = report.summary or ''
    summary = summary.replace('# ', '').replace('## ', '').replace('### ', '')
    summary_html = summary.replace('\n', '<br>')

    html = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;line-height:1.6;color:#333;background:#f5f5f5;margin:0;padding:20px 0;">
    <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
        <!-- 头部 -->
        <div style="background:linear-gradient(135deg,#0071e3 0%,#2997ff 100%);color:#fff;padding:30px;text-align:center;">
            <h1 style="margin:0;font-size:24px;font-weight:600;">📚 BookRank 畅销书周报</h1>
            <p style="margin:10px 0 0;font-size:14px;opacity:0.9;">{week_start} - {week_end} | 发布日期：{date_str}</p>
        </div>

        <!-- 内容 -->
        <div style="padding:30px;">
            <!-- 摘要 -->
            <div style="background:#f8f9fa;padding:15px;border-radius:8px;margin-bottom:25px;font-size:14px;line-height:1.7;">
                {summary_html}
            </div>

            {section_html('🏆 重要变化', top_changes)}
            {section_html('✨ 新上榜书籍', new_books)}
            {section_html('🚀 排名上升最快', top_risers)}
            {section_html('🏅 持续上榜最久', longest_running)}
            {section_html('💡 推荐书籍', featured_books)}
        </div>

        <!-- 底部 -->
        <div style="background:#f7fafc;padding:20px 30px;border-top:1px solid #e2e8f0;font-size:13px;color:#718096;text-align:center;">
            <p style="margin:0 0 8px;">📧 本邮件由 BookRank 自动化系统发送</p>
            <p style="margin:0;">© {datetime.now().year} BookRank - 纽约时报畅销书排行榜</p>
        </div>
    </div>
</body>
</html>'''
    return html


def send_weekly_report_email(report: WeeklyReport) -> bool:
    """发送周报邮件（使用标准库 smtplib，不依赖 Flask-Mail）

    参考 amazon_book_email.py 的实现方式。
    """
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from flask import current_app

    try:
        cfg = _get_smtp_config()

        # 检查配置
        if not cfg['username'] or not cfg['password']:
            logger.warning("邮件服务未配置（缺少 MAIL_USERNAME 或 MAIL_PASSWORD），跳过邮件发送")
            return False

        # 收件人
        recipients = [r.strip() for r in cfg['recipients'] if r.strip()]
        if not recipients:
            recipients = [cfg['sender']]

        # 构建邮件
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"【BookRank】{report.title}"
        msg['From'] = cfg['sender']
        msg['To'] = ', '.join(recipients)

        # 渲染 HTML
        html_body = _render_weekly_report_html(report)
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        # 发送（支持 TLS 和 SSL）
        context = ssl.create_default_context()
        port = int(cfg['port'])

        if port == 465:
            # SSL 直连（如 Gmail）
            with smtplib.SMTP_SSL(cfg['server'], port, context=context, timeout=30) as server:
                server.login(cfg['username'], cfg['password'])
                server.sendmail(cfg['sender'], recipients, msg.as_string())
        else:
            # STARTTLS（默认 587 端口）
            with smtplib.SMTP(cfg['server'], port, timeout=30) as server:
                server.starttls(context=context)
                server.login(cfg['username'], cfg['password'])
                server.sendmail(cfg['sender'], recipients, msg.as_string())

        logger.info(f"周报邮件发送成功: {report.title}, 收件人: {len(recipients)}")
        return True

    except Exception as e:
        logger.error(f"发送周报邮件时出错: {str(e)}")
        return False

def schedule_weekly_report():
    """调度周报生成任务"""
    # 这里可以使用任务调度器，如APScheduler
    # 例如：每天检查是否需要生成周报
    report = generate_weekly_report()
    return report
