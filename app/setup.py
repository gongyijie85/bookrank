"""
应用服务初始化和后台任务管理

从 app/__init__.py 拆分出来，降低主模块复杂度
使用 APScheduler 替代 daemon 线程，确保任务可管理和优雅关闭。
"""

import logging
import os
import threading
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .models.schemas import SystemConfig
from .services import (
    BookService,
    CacheService,
    FileCache,
    GoogleBooksClient,
    ImageCacheService,
    MemoryCache,
    NYTApiClient,
)
from .utils import RateLimiter
from .utils.error_handler import ErrorCategory, log_error
from .utils.service_helpers import register_service, require_service

logger = logging.getLogger(__name__)

# 全局调度器实例（应用生命周期内共享）
_scheduler: BackgroundScheduler | None = None

# 后台任务连续失败计数（Render 免费层已限制单 worker，内存计数可行）
_task_failure_counts: dict[str, int] = {}

# 外部触发的新书同步后台线程锁（防止重复启动；与 APScheduler 入口共用）
_auto_sync_lock = threading.Lock()


def init_services(app):
    """初始化业务服务（带容错：单个服务失败不影响其他服务）"""
    cfg = app.config

    memory_cache = MemoryCache(
        default_ttl=cfg['MEMORY_CACHE_TTL'],
        max_size=cfg.get('MEMORY_CACHE_MAX_SIZE', 1000),
    )
    file_cache = FileCache(cache_dir=cfg['CACHE_DIR'], default_ttl=cfg['CACHE_DEFAULT_TIMEOUT'])
    cache_service = CacheService(memory_cache, file_cache)
    register_service(app, 'cache_service', cache_service)
    app.logger.info('缓存服务初始化成功')

    nyt_client = _init_nyt_client(cfg, app)
    google_client = _init_google_client(cfg, app)
    image_cache = _init_image_cache(cfg, app)
    if image_cache:
        register_service(app, 'image_cache_service', image_cache)
    translation_service = _init_translation_service(app)

    _init_sync_request_gate(app)

    _init_new_book_modules(app, translation_service)

    book_service = _init_book_service(nyt_client, google_client, cache_service, image_cache, app, cfg)

    _init_recommendation_and_search_services(app, cfg)

    _start_background_tasks(app, book_service, translation_service, google_client)


def _init_recommendation_and_search_services(app, cfg):
    """初始化推荐和智能搜索服务（单例,挂到 app.extensions）"""
    try:
        from .services.recommendation_service import RecommendationService

        categories = cfg.get('CATEGORIES', {})
        register_service(app, 'recommendation_service', RecommendationService(categories))
        app.logger.info('推荐服务初始化成功（单例）')
    except Exception as e:
        log_error(ErrorCategory.UNKNOWN, f'推荐服务初始化失败: {e}', level='warning')

    try:
        from .services.smart_search_service import SmartSearchService

        categories = cfg.get('CATEGORIES', {})
        register_service(app, 'smart_search_service', SmartSearchService(categories))
        app.logger.info('智能搜索服务初始化成功（单例）')
    except Exception as e:
        log_error(ErrorCategory.UNKNOWN, f'智能搜索服务初始化失败: {e}', level='warning')


def _init_nyt_client(cfg, app):
    """初始化 NYT API 客户端"""
    try:
        rate_limiter = RateLimiter(max_calls=cfg['API_RATE_LIMIT'], window_seconds=cfg['API_RATE_LIMIT_WINDOW'])
        client = NYTApiClient(
            api_key=cfg.get('NYT_API_KEY', ''),
            base_url=cfg['NYT_API_BASE_URL'],
            rate_limiter=rate_limiter,
            timeout=cfg.get('API_TIMEOUT', 15),
            cache_ttl=cfg.get('NYT_CACHE_TTL', 86400 * 7),
        )
        app.logger.info('NYT API 客户端初始化成功')
        return client
    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'NYT API 客户端初始化失败: {e}', level='warning')
        return None


def _init_google_client(cfg, app):
    """初始化 Google Books API 客户端"""
    try:
        client = GoogleBooksClient(
            api_key=cfg.get('GOOGLE_API_KEY'),
            base_url=cfg['GOOGLE_BOOKS_API_URL'],
            timeout=cfg.get('API_TIMEOUT', 8),
            cache_ttl=cfg.get('GOOGLE_BOOKS_CACHE_TTL', 86400),
        )
        app.logger.info('Google Books 客户端初始化成功')
        return client
    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'Google Books 客户端初始化失败: {e}', level='warning')
        return None


def _init_image_cache(cfg, app):
    """初始化图片缓存服务"""
    try:
        return ImageCacheService(cache_dir=cfg['IMAGE_CACHE_DIR'], default_cover='/static/default-cover.png')
    except Exception as e:
        log_error(ErrorCategory.CACHE, f'图片缓存服务初始化失败: {e}', level='warning')
        return None


def _init_translation_service(app):
    """初始化翻译服务"""
    try:
        from .services.zhipu_translation_service import get_translation_service

        service = get_translation_service(app=app)
        register_service(app, 'translation_service', service)
        return service
    except Exception as e:
        log_error(ErrorCategory.TRANSLATION, f'翻译服务初始化失败: {e}', level='warning')
        return None


def _init_sync_request_gate(app):
    """注册同步请求闸门（无依赖，装配不可能失败；仍按惯例容错）。"""
    try:
        from .services.sync_request_gate import SyncRequestGate

        register_service(app, 'sync_request_gate', SyncRequestGate())
    except Exception as e:
        log_error(ErrorCategory.UNKNOWN, f'同步请求闸门初始化失败: {e}', level='warning')


def _init_new_book_modules(app, translation_service):
    """装配新书速递子模块并注册到 app.extensions（启动时一次性绑定翻译器）。"""
    try:
        from .services.new_book import create_new_book_modules

        modules = create_new_book_modules(translation_service=translation_service)
        register_service(app, 'new_book_modules', modules)
        app.logger.info('新书速递子模块初始化成功')
        return modules
    except Exception as e:
        # code review #154：装配失败时注册"空装配"降级（翻译器缺位），
        # 保证 require_service('new_book_modules') 不再抛错、相关路由不裸 500。
        # 仍只有装配工厂这一个装配入口。
        log_error(ErrorCategory.UNKNOWN, f'新书速递子模块装配失败，降级为空装配: {e}', level='warning')
        try:
            modules = create_new_book_modules(translation_service=None)
            register_service(app, 'new_book_modules', modules)
            return modules
        except Exception:
            log_error(ErrorCategory.UNKNOWN, '新书速递子模块降级装配也失败', level='error')
            return None


def _init_book_service(nyt_client, google_client, cache_service, image_cache, app, cfg):
    """初始化图书服务"""
    if not nyt_client or not cache_service:
        app.logger.warning('缺少 NYT 客户端或缓存服务，图书服务未初始化')
        return None

    try:
        book_service = BookService(
            nyt_client=nyt_client,
            google_client=google_client,
            cache_service=cache_service,
            image_cache=image_cache,
            app=app,
            max_workers=cfg['MAX_WORKERS'],
            categories=cfg['CATEGORIES'],
        )
        register_service(app, 'book_service', book_service)

        def _trigger_weekly_report():
            with app.app_context():
                try:
                    from .tasks.weekly_report_task import generate_weekly_report

                    app.logger.info('排行榜数据刷新，检查是否需要生成周报...')
                    generate_weekly_report()
                except Exception as e:
                    log_error(ErrorCategory.UNKNOWN, f'数据刷新触发周报生成失败: {e}')

        book_service.on_data_refreshed(_trigger_weekly_report)

        app.logger.info('图书服务初始化成功')
        return book_service
    except Exception as e:
        log_error(ErrorCategory.UNKNOWN, f'图书服务初始化失败: {e}')
        return None


# ==================== APScheduler 后台任务管理 ====================


def _start_background_tasks(app, book_service, translation_service, google_client):
    """
    使用 APScheduler 启动后台任务（替代旧的 daemon 线程）

    优势:
    - 任务无丢失（进程退出前自动等待）
    - 错失执行有容错（misfire_grace_time）
    - 防止重复执行（max_instances=1）
    - 统一管理（可暂停/恢复/移除）
    """
    global _scheduler

    if app.config.get('TESTING'):
        app.logger.info('⏸️ 测试环境跳过后台任务调度器')
        return

    if os.environ.get('DISABLE_BACKGROUND_THREADS', '').lower() == 'true':
        app.logger.info('⏸️ 后台任务已禁用（DISABLE_BACKGROUND_THREADS=true）')
        return

    if _scheduler and _scheduler.running:
        app.logger.warning('调度器已在运行，跳过重复初始化')
        return

    is_render_free = os.environ.get('RENDER', '').lower() == 'true'
    initial_delay = 120 if is_render_free else 300  # Render 免费层 2 分钟 / 其他 5 分钟
    cover_sync_delay = 120 if is_render_free else 60

    _scheduler = BackgroundScheduler(
        # daemon 线程：非 daemon 主循环线程会被 threading._shutdown 在 atexit 之前
        # join，导致解释器退出挂起（或退出时提交到期任务报 "cannot schedule new
        # futures after interpreter shutdown"）。运行中任务的完成等待由 atexit 注册的
        # shutdown_scheduler(wait=True) 保证。
        daemon=True,
        job_defaults={
            'coalesce': True,  # 合并错过的执行
            'max_instances': 1,  # 防止重叠执行
            'misfire_grace_time': 3600,  # 1小时内错过的允许补执行
        },
    )

    now = datetime.now()

    # 1. 周报启动检查（一次性，延迟执行）
    if book_service:
        _scheduler.add_job(
            func=_scheduler_wrapper(app, _weekly_report_task),
            trigger=DateTrigger(run_date=now, timezone=UTC),
            id='weekly_report_init',
            name='周报启动检查',
        )
        # DateTrigger with run_date=now fires immediately; we want delay
        # Remove and re-add with proper delay
        _scheduler.remove_job('weekly_report_init')

        from datetime import timedelta

        _scheduler.add_job(
            func=_scheduler_wrapper(app, _weekly_report_task),
            trigger=DateTrigger(run_date=now + timedelta(seconds=initial_delay), timezone=UTC),
            id='weekly_report_init',
            name='周报启动检查',
        )
        app.logger.info(f'📅 周报启动检查已安排（{initial_delay}秒后）')

    # 2. 新书速递自动同步（每天一次，翻译服务不可用时仍同步英文原始数据）
    from datetime import timedelta

    _scheduler.add_job(
        func=_scheduler_wrapper(app, _auto_sync_task),
        trigger=IntervalTrigger(hours=24, start_date=now + timedelta(seconds=initial_delay * 2), timezone=UTC),
        id='auto_sync',
        name='新书速递自动同步',
    )
    translation_status = '含翻译' if translation_service else '不含翻译'
    app.logger.info(f'📅 新书速递自动同步已安排（每天，首次{initial_delay * 2}秒后，{translation_status}）')

    # 3. NYT排行榜自动同步（每周一次）：刷新榜单、补充资料、翻译并写入语言包
    if book_service:
        from datetime import timedelta

        interval_days = app.config.get('NYT_RANKING_SYNC_DAYS', 7)
        _scheduler.add_job(
            func=_scheduler_wrapper(app, _nyt_ranking_sync_task),
            trigger=IntervalTrigger(
                days=interval_days,
                start_date=now + timedelta(seconds=initial_delay * 3),
                timezone=UTC,
            ),
            id='nyt_ranking_sync',
            name='NYT排行榜语言包同步',
        )
        app.logger.info(f'📅 NYT排行榜语言包同步已安排（每{interval_days}天，首次{initial_delay * 3}秒后）')

    # 4. 获奖书籍封面同步（每天一次，延迟执行）
    if google_client:
        from datetime import timedelta

        _scheduler.add_job(
            func=_scheduler_wrapper(app, _cover_sync_task),
            trigger=IntervalTrigger(
                days=1,
                start_date=now + timedelta(seconds=cover_sync_delay),
                timezone=UTC,
            ),
            id='cover_sync_init',
            name='获奖书籍封面同步',
        )
        app.logger.info(f'📅 获奖书籍封面同步已安排（每天一次，首次{cover_sync_delay}秒后）')

    # 5. 翻译缓存自动清理（每 30 分钟一次，避免限流中间件混杂非幂等副作用）
    if translation_service:
        from datetime import timedelta

        _scheduler.add_job(
            func=_scheduler_wrapper(app, _translation_cache_cleanup_task),
            trigger=IntervalTrigger(minutes=30, start_date=now + timedelta(seconds=600), timezone=UTC),
            id='translation_cache_cleanup',
            name='翻译缓存自动清理',
        )
        app.logger.info('📅 翻译缓存自动清理已安排（每30分钟，首次600秒后）')

    # 6. 翻译数据清理和预置获奖图书补种（一次性，延迟到后台执行，减轻冷启动负担）
    from datetime import timedelta

    _scheduler.add_job(
        func=_scheduler_wrapper(app, _deferred_init_task),
        trigger=DateTrigger(run_date=now + timedelta(seconds=initial_delay + 60), timezone=UTC),
        id='deferred_init',
        name='延迟初始化（翻译清理+预置数据）',
    )
    app.logger.info(f'📅 延迟初始化已安排（{initial_delay + 60}秒后）')

    # 7. 获奖图书自动刷新（每周一次，从 Wikidata 同步最新获奖数据）
    from datetime import timedelta

    _scheduler.add_job(
        func=_scheduler_wrapper(app, _award_refresh_task),
        trigger=IntervalTrigger(
            days=7,
            start_date=now + timedelta(seconds=initial_delay * 4),
            timezone=UTC,
        ),
        id='award_refresh',
        name='获奖图书自动刷新（Wikidata）',
    )
    app.logger.info(f'📅 获奖图书自动刷新已安排（每7天，首次{initial_delay * 4}秒后）')

    _scheduler.start()
    app.logger.info('✅ APScheduler 后台任务调度器已启动')


def _scheduler_wrapper(app, task_func):
    """
    为 APScheduler job 创建包装函数
    - 自动创建 app context
    - 捕获所有异常（防止调度器崩溃）
    - 连续失败时发送告警通知
    """

    def wrapper():
        task_name = task_func.__name__
        try:
            with app.app_context():
                task_func(app)
            # 成功后重置失败计数
            _task_failure_counts.pop(task_name, None)
        except Exception as e:
            log_error(ErrorCategory.UNKNOWN, f'后台任务 [{task_name}] 失败: {e}', exc_info=True)
            _track_task_failure(app, task_name, str(e))

    wrapper.__name__ = task_func.__name__
    return wrapper


def _track_task_failure(app, task_name: str, error_message: str) -> None:
    """记录后台任务失败，连续失败达到阈值时触发告警"""
    _task_failure_counts[task_name] = _task_failure_counts.get(task_name, 0) + 1
    count = _task_failure_counts[task_name]
    try:
        from .models import db

        SystemConfig.set_value(f'last_failure_count_{task_name}', str(count))
        db.session.commit()
    except Exception as err:
        logger.warning('记录失败计数失败: %s', err)
        try:
            from .models import db

            db.session.rollback()
        except Exception:
            pass

    if count >= 2:
        _notify_task_failure(app, task_name, count, error_message)


def _notify_task_failure(app, task_name: str, failure_count: int, error_message: str) -> None:
    """发送后台任务失败告警（webhook 优先，邮件兜底）"""
    webhook_url = os.environ.get('ALERT_WEBHOOK_URL')
    if webhook_url:
        try:
            import requests

            payload = {
                'task': task_name,
                'failure_count': failure_count,
                'error': error_message[:500],
                'timestamp': datetime.now(UTC).isoformat(),
            }
            requests.post(webhook_url, json=payload, timeout=10)
            logger.warning('已发送后台任务失败告警: %s', task_name)
        except Exception as exc:
            logger.warning('告警 webhook 发送失败: %s', exc)
        return

    # 邮件兜底
    if app.config.get('MAIL_ENABLED'):
        try:
            from flask_mail import Message

            mail = app.extensions.get('mail')
            if not mail:
                return
            subject = f'[BookRank 告警] 后台任务 {task_name} 连续失败 {failure_count} 次'
            body = f"""任务: {task_name}
连续失败次数: {failure_count}
错误摘要: {error_message[:500]}
时间: {datetime.now(UTC).isoformat()}
请尽快查看 Render 日志。
"""
            recipients = app.config.get('MAIL_RECIPIENTS', '').split(',')
            if recipients and recipients[0]:
                msg = Message(subject, recipients=recipients, body=body)
                mail.send(msg)
                logger.warning('已发送后台任务失败邮件告警: %s', task_name)
        except Exception as exc:
            logger.warning('告警邮件发送失败: %s', exc)


def _translation_cache_cleanup_task(app):
    """翻译缓存自动清理任务（替代旧的限流中间件副作用）"""
    try:
        with app.app_context():
            from .services.translation_cache_service import get_translation_cache_service

            cache_svc = get_translation_cache_service()
            if cache_svc:
                cache_svc.auto_cleanup(max_items=8000, keep_recent_days=30)
                app.logger.info('翻译缓存自动清理完成')
    except Exception as e:
        log_error(ErrorCategory.CACHE, f'翻译缓存自动清理跳过: {e}', level='warning')


def _deferred_init_task(app):
    """延迟初始化任务：翻译数据清理 + 预置获奖图书补种（从冷启动路径移出）"""
    try:
        from run import _cleanup_dirty_translations

        with app.app_context():
            _cleanup_dirty_translations()
    except Exception as e:
        log_error(ErrorCategory.UNKNOWN, f'翻译脏数据清理跳过: {e}', level='warning')

    try:
        from app.initialization.sample_award_books import init_sample_award_books

        with app.app_context():
            init_sample_award_books(app)
            logger.info('预置获奖图书补种完成')
    except Exception as e:
        log_error(ErrorCategory.UNKNOWN, f'预置获奖图书补种跳过: {e}', level='warning')


def shutdown_scheduler(app):
    """优雅关闭调度器（在应用退出时调用）"""
    global _scheduler
    if _scheduler and _scheduler.running:
        app.logger.info('正在关闭 APScheduler...')
        _scheduler.shutdown(wait=True)
        _scheduler = None
        app.logger.info('✅ APScheduler 已关闭')


# ==================== 任务函数（与原实现一致） ====================


def _weekly_report_task(app):
    """周报自动生成任务"""
    try:
        from .tasks.weekly_report_task import generate_weekly_report

        app.logger.info('开始自动生成周报...')
        report = generate_weekly_report()
        if report:
            app.logger.info(f'周报生成成功: {report.title}')
        else:
            app.logger.warning('周报生成失败或已存在')
    except Exception as e:
        log_error(ErrorCategory.UNKNOWN, f'自动生成周报失败: {e}', exc_info=True)
        _log_failure(app, 'last_report_failure')


def run_auto_sync() -> dict:
    """执行新书速递自动同步的核心逻辑。

    供 APScheduler 定时器（_auto_sync_task）与外部 cron 触发端点
    （/api/cron/trigger-new-books-sync）共用。内置 24 小时自我节流，
    两套触发机制并存也不会重复同步。

    返回结构包含 status（skipped/synced/partial）与统计数据；
    异常向上抛出，由调用方决定日志与失败记录策略。
    """
    from flask import current_app

    modules = require_service('new_book_modules')

    last_sync = SystemConfig.get_value('last_auto_sync_time')
    if last_sync:
        last_sync_time = datetime.fromisoformat(last_sync)
        if last_sync_time.tzinfo is None:
            last_sync_time = last_sync_time.replace(tzinfo=UTC)
        hours_since = (datetime.now(UTC) - last_sync_time).total_seconds() / 3600
        if hours_since < 24:
            return {'status': 'skipped', 'reason': f'距离上次同步仅 {hours_since:.1f} 小时'}

    current_app.logger.info('开始自动同步新书数据...')
    modules.publisher_manager.init_publishers()
    results = modules.sync_engine.sync_all_publishers(max_books_per_publisher=15, batch_size=1)

    total_added = sum(r.get('added', 0) for r in results)
    total_updated = sum(r.get('updated', 0) for r in results)
    failed_results = [result for result in results if result.get('success') is False]

    # 持久化本次同步摘要，便于生产诊断（哪家失败/超时、各自耗时）
    # SystemConfig.set_value 只写 session，必须 commit 后 last-sync 端点才能读到。
    try:
        import json as _json

        from .models import db

        if results and not failed_results:
            SystemConfig.set_value('last_auto_sync_time', datetime.now(UTC).isoformat())

        # 工单 #83：Google Books 系日期过滤拒绝计数的字段名（仅 Google 系
        # 爬虫的同步结果字典携带），随各家条目写入摘要供 2 周观测期判定
        _date_filter_keys = (
            'traversed_total',
            'rejected_no_date',
            'rejected_unparseable',
            'rejected_out_of_window',
            'rejected_future_placeholder',
            'accepted_year_only',
        )
        publishers_summary = []
        for r in results:
            entry = {
                'publisher': r.get('publisher'),
                'status': r.get('status'),
                'elapsed_seconds': r.get('elapsed_seconds'),
                'added': r.get('added', 0),
                'error': (r.get('error') or '')[:200] or None,
            }
            if 'traversed_total' in r:
                entry['date_filter'] = {k: r[k] for k in _date_filter_keys if k in r}
            publishers_summary.append(entry)

        summary = {
            'finished_at': datetime.now(UTC).isoformat(),
            'added': total_added,
            'updated': total_updated,
            'publishers': publishers_summary,
        }
        SystemConfig.set_value('last_auto_sync_result', _json.dumps(summary, ensure_ascii=False))
        db.session.commit()
    except Exception as e:
        current_app.logger.warning(f'保存同步摘要失败: {e}')
        try:
            from .models import db

            db.session.rollback()
        except Exception:
            pass

    return {
        'status': 'synced' if not failed_results else 'partial',
        'added': total_added,
        'updated': total_updated,
        'failed_publishers': len(failed_results),
        'total_publishers': len(results),
    }


def _auto_sync_task(app):
    """新书速递自动同步任务（APScheduler 兜底入口）"""
    if not _auto_sync_lock.acquire(blocking=False):
        app.logger.info('新书同步已有实例在运行，跳过本次调度')
        return
    try:
        result = run_auto_sync()
        if result['status'] == 'skipped':
            app.logger.info(f'{result["reason"]}，跳过')
        else:
            if result['failed_publishers']:
                app.logger.warning(
                    '自动同步未完全成功，不更新 last_auto_sync_time：失败出版社 %s/%s',
                    result['failed_publishers'],
                    result['total_publishers'],
                )
            app.logger.info(f'自动同步完成：新增 {result["added"]} 本，更新 {result["updated"]} 本')
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'自动同步失败: {e}', exc_info=True)
        _log_failure(app, 'last_sync_failure')
    finally:
        _auto_sync_lock.release()


def trigger_auto_sync_background(app) -> dict:
    """在后台线程中启动新书同步，立即返回（供外部 cron 端点调用）。

    全量同步约 4 分钟，超过 Gunicorn timeout（180秒），不能同步等待。
    复用 _auto_sync_task（含锁、节流、异常处理与失败记录）。

    返回 {'status': 'started'} 或 {'status': 'already_running'}。
    """
    if _auto_sync_lock.locked():
        return {'status': 'already_running'}

    def _run():
        with app.app_context():
            _auto_sync_task(app)

    thread = threading.Thread(target=_run, daemon=True, name='auto-sync-cron')
    thread.start()
    return {'status': 'started'}


def _nyt_ranking_sync_task(app):
    """NYT排行榜自动同步任务：强制刷新榜单并写入中文语言包。"""
    try:
        from .utils.service_helpers import get_service

        service = get_service('book_service')
        if not service:
            app.logger.warning('缺少 BookService，跳过NYT排行榜同步')
            return

        interval_days = int(app.config.get('NYT_RANKING_SYNC_DAYS', 7))
        last_sync = SystemConfig.get_value('last_nyt_ranking_sync_time')
        if last_sync:
            last_sync_time = datetime.fromisoformat(last_sync)
            if last_sync_time.tzinfo is None:
                last_sync_time = last_sync_time.replace(tzinfo=UTC)
            days_since = (datetime.now(UTC) - last_sync_time).days
            if days_since < interval_days:
                app.logger.info(f'距离上次NYT同步仅 {days_since} 天，跳过')
                return

        app.logger.info('开始自动同步NYT排行榜并写入语言包...')
        results = service.sync_all_categories(
            force_refresh=True,
            translate=True,
            translator=get_service('translation_service'),
        )

        successful = [result for result in results if result.get('success')]
        total_books = sum(result.get('books', 0) for result in successful)
        metadata_saved = sum(result.get('metadata_saved', 0) for result in successful)
        translated_fields = sum(result.get('language_pack', {}).get('fields_translated', 0) for result in successful)
        failures = [result for result in results if not result.get('success')]

        if successful:
            from .models import db

            SystemConfig.set_value('last_nyt_ranking_sync_time', datetime.now(UTC).isoformat())
            db.session.commit()

        if failures:
            app.logger.warning('NYT排行榜同步部分失败：%s/%s 个分类失败', len(failures), len(results))
            _log_failure(app, 'last_nyt_ranking_sync_failure')

        app.logger.info(
            'NYT排行榜同步完成：分类%s个, 图书%s本, 元数据%s条, 翻译字段%s个',
            len(successful),
            total_books,
            metadata_saved,
            translated_fields,
        )

    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'NYT排行榜同步失败: {e}', exc_info=True)
        _log_failure(app, 'last_nyt_ranking_sync_failure')


def _cover_sync_task(app):
    """获奖书籍封面自动同步任务"""
    try:
        from .services.award_cover_sync_service import AwardCoverSyncService
        from .utils.service_helpers import get_service

        app.logger.info('开始检查获奖书籍封面...')

        from .utils.service_helpers import get_or_create_google_books_client

        google_client = get_or_create_google_books_client()

        sync_service = AwardCoverSyncService(
            google_client,
            image_cache=get_service('image_cache_service'),
        )

        result = sync_service.sync_missing_covers(batch_size=30, delay=0.5)

        if result.get('status') == 'success':
            app.logger.info(f'封面同步完成: 更新{result.get("updated", 0)}本, 跳过{result.get("skipped", 0)}本')
        elif result.get('status') == 'complete':
            app.logger.info('所有获奖书籍封面已完整')
        else:
            app.logger.warning(f'封面同步状态: {result.get("status")}')

    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'封面同步失败: {e}', exc_info=True)


def _award_refresh_task(app):
    """获奖图书自动刷新任务 — 从 Wikidata 同步最新获奖数据（每月执行）"""
    try:
        from datetime import datetime as _dt

        from .services.award_book_service import AwardBookService

        app.logger.info('开始检查获奖图书数据更新...')

        current_year = _dt.now().year
        service = AwardBookService(app)
        result = service.refresh_award_books(
            start_year=2020,
            end_year=current_year,  # 自动使用当前年份
            force=False,  # 尊重刷新间隔，避免频繁调用 Wikidata
        )

        if result.get('status') == 'skipped':
            app.logger.info(f'获奖图书刷新跳过: {result.get("message", "未达到刷新间隔")}')
        else:
            app.logger.info(
                f'获奖图书刷新完成: 新增 {result.get("new_books", 0)} 本, '
                f'更新 {result.get("updated_books", 0)} 本, '
                f'失败 {result.get("failed_books", 0)} 本'
            )
            if result.get('errors'):
                for err in result['errors'][:3]:
                    app.logger.warning(f'  ⚠️ {err}')

    except Exception as e:
        log_error(ErrorCategory.API_CALL, f'获奖图书自动刷新失败: {e}', exc_info=True)


def _log_failure(app, key: str):
    """记录失败时间到系统配置"""
    try:
        from .models import db

        SystemConfig.set_value(key, datetime.now(UTC).isoformat())
        db.session.commit()
    except Exception as err:
        log_error(ErrorCategory.DB_QUERY, f'记录失败时间失败: {err}')
        try:
            from .models import db

            db.session.rollback()
        except Exception:
            pass
