"""N+1 回归保护（ROADMAP 5）：获奖书单与新书速递查询的断言计数。

通过 SQLAlchemy 事件监听统计查询条数：get_award_books /
search_award_books 在访问 book.award 时不得触发逐行懒加载。
"""

import pytest

from app.models.schemas import Award, AwardBook
from app.services.award_book_service import AwardBookService


class _QueryCounter:
    """监听 SQLAlchemy 的 SELECT 语句并计数。"""

    def __init__(self):
        self.count = 0
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        event.listen(Engine, 'before_cursor_execute', self._on_execute)

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            self.count += 1

    def stop(self):
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        event.remove(Engine, 'before_cursor_execute', self._on_execute)


@pytest.fixture
def sample_data(app, db):
    with app.app_context():
        awards = [
            Award(name=f'测试奖-{i}', description='desc', country='US') for i in range(3)
        ]
        db.session.add_all(awards)
        db.session.commit()
        for idx, award in enumerate(awards):
            db.session.add(
                AwardBook(
                    award_id=award.id,
                    year=2024 - idx,
                    category='Novel',
                    rank=idx + 1,
                    title=f'Book-{idx}',
                    author=f'Author-{idx}',
                    is_displayable=True,
                )
            )
        db.session.commit()


def test_get_award_books_no_n_plus_one(app, db, sample_data):
    """3 本书 + award 关系：总查询数应为 3 以内（1 列表 + 1 count + 1 预加载）。"""
    with app.app_context():
        service = AwardBookService(app=app)
        counter = _QueryCounter()
        try:
            books, total = service.get_award_books(include_displayable_only=True, limit=10)
            # 访问关系的属性，触发真实懒加载（若未预加载会 +N）
            for book in books:
                _ = book.award.name
        finally:
            counter.stop()

        assert total >= 3
        # count(1) + 主查询(1) + selectinload(1) <= 3；懒加载复发则 >= 4
        assert counter.count <= 3, f'N+1 复发：{counter.count} 条查询'


def test_search_award_books_no_n_plus_one(app, db, sample_data):
    with app.app_context():
        service = AwardBookService(app=app)
        counter = _QueryCounter()
        try:
            books, _ = service.search_award_books('Book', limit=10)
            for book in books:
                _ = book.award.name
        finally:
            counter.stop()
        assert counter.count <= 3, f'N+1 复发：{counter.count} 条查询'
