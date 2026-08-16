import hashlib
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..services.new_book import NewBookModules

from flask import current_app, request

from ..services.google_books_client import GoogleBooksClient

_background_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='bookrank-bg')


def submit_background_task(fn: Any, *args: Any, **kwargs: Any) -> Future:
    return _background_executor.submit(fn, *args, **kwargs)


def register_service(app: Any, name: str, service: Any) -> None:
    app.extensions[name] = service


def get_service(name: str) -> Any | None:
    """按名称获取已注册服务单例，缺失时返回 None"""
    return current_app.extensions.get(name)


def require_service(name: str, display_name: str = '') -> Any:
    """按名称获取已注册服务单例，缺失时抛出 RuntimeError"""
    service = get_service(name)
    if service is None:
        label = display_name or name.replace('_', ' ')
        raise RuntimeError(f'{label}未初始化，请检查应用配置')
    return service


def get_new_book_modules() -> 'NewBookModules':
    """获取已注册的新书速递子模块持有对象（SyncEngine/Query/PublisherManager/TranslationPipeline）。"""
    return require_service('new_book_modules')


def get_sync_request_gate() -> Any:
    """获取已注册的同步请求闸门（冷却/锁/播种一次性化）。"""
    return require_service('sync_request_gate')


def _get_or_create_service(name: str, factory_path: str):
    """获取已注册服务；若未注册则按当前 CATEGORIES 兜底创建"""
    svc = get_service(name)
    if svc is not None:
        return svc
    module_path, class_name = factory_path.rsplit('.', 1)
    module = __import__(module_path, fromlist=[class_name])
    factory = getattr(module, class_name)
    categories = current_app.config.get('CATEGORIES', {})
    return factory(categories)


def get_or_create_recommendation_service() -> Any:
    """获取已注册的 RecommendationService；若未注册则按当前 CATEGORIES 兜底创建"""
    return _get_or_create_service('recommendation_service', 'app.services.recommendation_service.RecommendationService')


def get_or_create_smart_search_service() -> Any:
    """获取已注册的 SmartSearchService；若未注册则按当前 CATEGORIES 兜底创建"""
    return _get_or_create_service('smart_search_service', 'app.services.smart_search_service.SmartSearchService')


def get_or_create_google_books_client() -> GoogleBooksClient:
    """获取 GoogleBooksClient，若未初始化则创建兜底实例"""
    client = get_google_books_client()
    if client:
        return client
    from ..config import Config
    from ..services.google_books_client import GoogleBooksClient

    return GoogleBooksClient(
        api_key=Config.GOOGLE_API_KEY,
        base_url='https://www.googleapis.com/books/v1/volumes',
    )


def get_google_books_client() -> GoogleBooksClient | None:
    book_service = get_service('book_service')
    if book_service and hasattr(book_service, '_google_client'):
        return book_service._google_client
    return None


def hash_client_ip(raw_ip: str | None = None) -> str | None:
    """对客户端 IP 进行 SHA-256 哈希（隐私保护）"""
    if raw_ip is None:
        raw_ip = request.remote_addr
    if not raw_ip:
        return None
    return hashlib.sha256((raw_ip or 'unknown').encode()).hexdigest()[:16]
