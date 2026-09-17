"""后台执行路径必须自带 app context（回归：#218 之后的代码审查）。

ThreadPoolExecutor 与裸 threading.Thread 里都没有请求上下文：

- `db.session` 是 Flask-SQLAlchemy 绑定 app context 的 scoped session；
- `require_service()` 走 `current_app`。

两处都会抛 RuntimeError，而调用方各自的 `except` 把它记成 warning / "服务未初始化" ——
于是功能**静默消失**：不报错、不 500，只是永远不发生。本文件的用例把提交出去的闭包
放到一个真正没有上下文的线程里执行，因此修复前必然失败。
"""

import threading
from types import SimpleNamespace

import pytest
from flask import current_app

from app.models.database import db
from app.models.new_book import NewBook, Publisher

_RealThread = threading.Thread  # 导入时绑定真身：test2 会把 threading.Thread 换成记录器


def _in_bare_thread(fn):
    """在确实没有 app context 的线程里跑 fn，返回 (异常或 None, 副作用盒)。"""
    box = {}
    result = {}

    def target():
        try:
            fn()
            result['error'] = None
        except BaseException as exc:
            result['error'] = exc
        result['box'] = box

    t = _RealThread(target=target)
    t.start()
    t.join(15)
    assert not t.is_alive(), '后台任务疑似挂死'
    return result


class _StubTranslator:
    def translate(self, text, source_lang, target_lang, field_type=None):
        return f'译文-{field_type}'


def _make_book():
    publisher = Publisher(name='测试出版社', name_en='Test Publisher', crawler_class='stub')
    db.session.add(publisher)
    db.session.flush()  # 取到自增主键，否则 publisher_id 仍是 None
    book = NewBook(
        title='A Very Long English Title',
        author='A. N. Author',
        description='English blurb',
        title_zh=None,
        description_zh=None,
        publisher_id=publisher.id,
    )
    db.session.add(book)
    db.session.commit()
    return book.id


@pytest.mark.usefixtures('db')
def test_background_translation_runs_with_context(app, db, client, monkeypatch):
    """GET /new-book/<id> 提交的后台翻译必须真的写回 title_zh。"""
    from app.routes import main as main_routes
    from app.services.new_book.translation_pipeline import TranslationPipeline

    with app.app_context():
        book_id = _make_book()

    submitted = []
    monkeypatch.setattr(main_routes, 'submit_background_task', lambda fn, *a, **k: submitted.append(fn))
    # 路由的模板渲染不在本用例范围内，避免为无关字段造一堆假数据
    monkeypatch.setattr(main_routes, 'render_adaptive', lambda *a, **k: 'ok')
    stub_translator = _StubTranslator()
    modules = SimpleNamespace(
        translation_pipeline=TranslationPipeline(stub_translator, None),
        query_service=SimpleNamespace(get_book=lambda bid: db.session.get(NewBook, bid)),
    )
    monkeypatch.setattr(main_routes, 'get_new_book_modules', lambda: modules)
    monkeypatch.setattr(main_routes, 'get_service', lambda name: stub_translator)

    resp = client.get(f'/new-book/{book_id}')
    assert resp.status_code == 200
    assert len(submitted) == 1, '路由未提交后台翻译任务'

    out = _in_bare_thread(submitted[0])
    assert out['error'] is None, f'后台任务在没有上下文时抛出：{out["error"]!r}'

    with app.app_context():
        fresh = db.session.get(NewBook, book_id)
        assert fresh is not None
        assert fresh.title_zh == '译文-title', f'title_zh 未被后台补齐：{fresh.title_zh!r}'
        assert fresh.description_zh == '译文-description'


def test_weekly_self_heal_thread_runs_with_context(app, monkeypatch):
    """周报自愈线程必须能在无上下文线程里真正调到 generate_weekly_report。"""
    import app.tasks.weekly_report_task as task_mod
    from app.services.weekly_report_service import WeeklyReportService

    seen = {}

    def fake_generate(force_regenerate=False):
        # 有上下文时 _get_current_object() 正常；没有则抛 RuntimeError
        seen['app'] = current_app._get_current_object()
        return None

    captured = {}

    class _RecordingThread:
        def __init__(self, target=None, **kwargs):
            captured['target'] = target

        def start(self):
            pass  # 不真跑：由下面的 _in_bare_thread 在干净线程里执行

        def join(self, timeout=None):
            pass

    monkeypatch.setattr(task_mod, 'generate_weekly_report', fake_generate)
    monkeypatch.setattr(task_mod, '_last_report_trigger_time', 0.0)
    monkeypatch.setattr(threading, 'Thread', _RecordingThread)

    svc = WeeklyReportService(book_service=SimpleNamespace())
    monkeypatch.setattr(svc, 'get_report_by_week_end', lambda week_end: None)
    monkeypatch.setattr(svc, 'get_latest_report', lambda: None)

    with app.app_context():
        latest, generating = svc.get_or_trigger_current_week_report()
    assert generating is True
    assert 'target' in captured, '自愈未启动后台线程'

    out = _in_bare_thread(captured['target'])
    assert out['error'] is None, f'自愈线程抛出：{out["error"]!r}'
    assert 'app' in seen, 'generate_weekly_report 从未被执行（上下文缺失被 except 吞掉了）'
    assert seen['app'] is app
