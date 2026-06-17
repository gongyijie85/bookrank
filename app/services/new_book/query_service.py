import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from ...models.database import db
from ...models.new_book import NewBook, Publisher
from .translation_pipeline import TranslationPipeline

logger = logging.getLogger(__name__)


class NewBookQueryService:
    def __init__(self, translation_pipeline: TranslationPipeline) -> None:
        self._translation_pipeline = translation_pipeline

    def get_new_books(
        self,
        publisher_id: int | None = None,
        category: str | None = None,
        days: int = 30,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[NewBook], int]:
        from sqlalchemy.orm import joinedload

        query = NewBook.query.options(joinedload(NewBook.publisher)).filter(NewBook.is_displayable.is_(True))

        query = self._apply_publication_window(query, days)

        if publisher_id:
            query = query.filter(NewBook.publisher_id == publisher_id)

        if category:
            query = query.filter(NewBook.category == category)

        query = query.order_by(NewBook.publication_date.desc().nullslast(), NewBook.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        self._translation_pipeline._hydrate_language_pack(pagination.items)

        return pagination.items, pagination.total

    def get_book(self, book_id: int) -> NewBook | None:
        from sqlalchemy.orm import joinedload

        book = NewBook.query.options(joinedload(NewBook.publisher)).get(book_id)
        if book:
            self._translation_pipeline._hydrate_language_pack([book])
        return book

    def search_books(
        self,
        keyword: str,
        page: int = 1,
        per_page: int = 20,
        publisher_id: int | None = None,
        category: str | None = None,
        days: int | None = None,
    ) -> tuple[list[NewBook], int]:
        from sqlalchemy.orm import joinedload

        search_pattern = f'%{keyword}%'

        query = (
            NewBook.query.options(joinedload(NewBook.publisher))
            .filter(
                db.or_(
                    NewBook.title.ilike(search_pattern),
                    NewBook.title_zh.ilike(search_pattern),
                    NewBook.author.ilike(search_pattern),
                    NewBook.isbn13 == keyword,
                    NewBook.isbn10 == keyword,
                )
            )
            .filter(NewBook.is_displayable.is_(True))
        )

        if publisher_id:
            query = query.filter(NewBook.publisher_id == publisher_id)

        if category:
            query = query.filter(NewBook.category == category)

        if days is not None:
            query = self._apply_publication_window(query, days)

        query = query.order_by(NewBook.publication_date.desc().nullslast(), NewBook.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        self._translation_pipeline._hydrate_language_pack(pagination.items)

        return pagination.items, pagination.total

    def get_categories(self) -> list[dict[str, str]]:
        from sqlalchemy import func

        results = (
            db.session.query(NewBook.category, func.count(NewBook.id).label('count'))
            .filter(NewBook.category.isnot(None), NewBook.is_displayable.is_(True))
            .group_by(NewBook.category)
            .order_by(func.count(NewBook.id).desc())
            .all()
        )

        return [{'name': r.category, 'count': r.count} for r in results]

    def get_statistics(self) -> dict[str, Any]:
        from sqlalchemy import func

        total_books = NewBook.query.count()
        total_publishers = Publisher.query.count()
        active_publishers = Publisher.query.filter_by(is_active=True).count()

        today = datetime.now(UTC).date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        recent_books_7d = NewBook.query.filter(
            NewBook.is_displayable.is_(True),
            NewBook.publication_date >= week_ago,
            NewBook.publication_date <= today,
        ).count()

        recent_books_30d = NewBook.query.filter(
            NewBook.is_displayable.is_(True),
            NewBook.publication_date >= month_ago,
            NewBook.publication_date <= today,
        ).count()

        category_stats = (
            db.session.query(NewBook.category, func.count(NewBook.id).label('count'))
            .filter(NewBook.category.isnot(None))
            .group_by(NewBook.category)
            .order_by(func.count(NewBook.id).desc())
            .limit(10)
            .all()
        )

        return {
            'total_books': total_books,
            'total_publishers': total_publishers,
            'active_publishers': active_publishers,
            'recent_books_7d': recent_books_7d,
            'recent_books_30d': recent_books_30d,
            'top_categories': [{'category': c.category, 'count': c.count} for c in category_stats],
        }

    @staticmethod
    def _apply_publication_window(query, days: int):
        today = datetime.now(UTC).date()
        cutoff_date = today - timedelta(days=days)
        cutoff_datetime = datetime.combine(cutoff_date, datetime.min.time()).replace(tzinfo=UTC)
        tomorrow_datetime = datetime.combine(today + timedelta(days=1), datetime.min.time()).replace(tzinfo=UTC)

        return query.filter(  # type: ignore[union-attr,operator]
            db.or_(
                db.and_(
                    NewBook.publication_date.isnot(None),
                    NewBook.publication_date >= cutoff_date,  # type: ignore[operator]
                    NewBook.publication_date <= today,  # type: ignore[operator]
                ),
                db.and_(
                    NewBook.publication_date.is_(None),
                    NewBook.created_at >= cutoff_datetime,
                    NewBook.created_at < tomorrow_datetime,
                ),
            )
        )
