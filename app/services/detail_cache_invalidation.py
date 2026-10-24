"""Expire application-memory detail snapshots after committed database writes."""

from threading import Lock
from typing import Any

from flask import current_app, has_app_context
from sqlalchemy import event, inspect
from sqlalchemy.orm import ORMExecuteState, Session, SessionTransaction

from ..models.database import db
from ..models.new_book import NewBook, Publisher
from ..models.schemas import Award, AwardBook, BookMetadata, TranslationCache

_PENDING_KEY = 'book_detail_cache_invalidations'
_install_lock = Lock()
_installed = False
_PUBLIC_NEW_BOOK_NAMESPACES = {
    'public-new-book-categories',
    'public-new-book-statistics',
    'public-publisher-book-counts',
}
_BULK_NAMESPACES = {
    'award_books': {'award', 'similarity', 'award-cover'},
    'awards': {'award', 'similarity', 'award-cover'},
    'new_books': {'new-book', *_PUBLIC_NEW_BOOK_NAMESPACES},
    'publishers': {'new-book', *_PUBLIC_NEW_BOOK_NAMESPACES},
    'book_metadata': {'bestseller', 'book-api', 'language-metadata'},
    'translation_cache': {'new-book', 'bestseller', 'book-api', 'language-text'},
}


def has_uncommitted_cache_writes() -> bool:
    """写事务读取自身变更时不能使用或填充跨请求共享缓存。"""
    if not has_app_context():
        return False
    session = db.session()
    return bool(session.new or session.dirty or session.deleted or session.info.get(_PENDING_KEY))


def _cache() -> Any:
    return current_app.extensions.get('book_detail_cache') if has_app_context() else None


def _remember(session: Session, changes: set[tuple[str, Any]]) -> None:
    transaction = session.get_nested_transaction() or session.get_transaction()
    if transaction is None or not changes:
        return
    pending = session.info.setdefault(_PENDING_KEY, {})
    pending.setdefault(transaction, set()).update(changes)


def _after_flush(session: Session, flush_context: Any) -> None:
    if _cache() is None:
        session.info.pop(_PENDING_KEY, None)
        return
    changes: set[tuple[str, Any]] = set()
    for record in session.new | session.dirty | session.deleted:
        if isinstance(record, AwardBook):
            changes.update({('award', record.id), ('similarity', None), ('award-cover', record.id)})
        elif isinstance(record, Award):
            changes.update({('award', None), ('similarity', None), ('award-cover', None)})
        elif isinstance(record, NewBook):
            changes.add(('new-book', record.id))
            changes.update((namespace, None) for namespace in _PUBLIC_NEW_BOOK_NAMESPACES)
        elif isinstance(record, Publisher):
            changes.add(('new-book', None))
            changes.update((namespace, None) for namespace in _PUBLIC_NEW_BOOK_NAMESPACES)
        elif isinstance(record, BookMetadata):
            changes.add(('language-metadata', None))
            previous_isbns: list[str] = list(inspect(record).attrs.isbn.history.deleted)
            for isbn in [record.isbn, *previous_isbns]:
                changes.update({('bestseller', isbn), ('book-api', isbn)})
        elif isinstance(record, TranslationCache):
            changes.update({('new-book', None), ('bestseller', None), ('book-api', None), ('language-text', None)})
    _remember(session, changes)


def _after_commit(session: Session) -> None:
    cache = _cache()
    if cache is None:
        session.info.pop(_PENDING_KEY, None)
        return
    pending = session.info.get(_PENDING_KEY)
    if not pending:
        return
    transaction = session.get_nested_transaction() or session.get_transaction()
    if transaction is None:
        return
    changes = pending.pop(transaction, set())
    if transaction.parent is not None:
        pending.setdefault(transaction.parent, set()).update(changes)
        return
    session.info.pop(_PENDING_KEY, None)
    if changes:
        cache.invalidate(
            lambda key: any(
                key[0] == namespace and (identifier is None or key[1] == identifier)
                for namespace, identifier in changes
            )
        )


def _after_soft_rollback(session: Session, previous_transaction: SessionTransaction) -> None:
    if previous_transaction.parent is None:
        session.info.pop(_PENDING_KEY, None)
        return
    pending = session.info.get(_PENDING_KEY)
    if pending:
        pending.pop(previous_transaction, None)


def _do_orm_execute(state: ORMExecuteState) -> Any:
    if _cache() is None:
        state.session.info.pop(_PENDING_KEY, None)
        return None
    if not (state.is_insert or state.is_update or state.is_delete):
        return None
    table = getattr(state.statement, 'table', None)
    namespaces = _BULK_NAMESPACES.get(getattr(table, 'name', ''))
    if not namespaces:
        return None
    # invoke_statement starts the transaction and raises on a failed write, so
    # only successful DML contributes invalidations to the eventual commit.
    result = state.invoke_statement()
    _remember(state.session, {(namespace, None) for namespace in namespaces})
    return result


def init_detail_cache_invalidation() -> None:
    """Install global listeners once; each operation uses its active Flask app."""
    global _installed
    with _install_lock:
        if _installed:
            return
        event.listen(Session, 'after_flush', _after_flush)
        event.listen(Session, 'after_commit', _after_commit)
        event.listen(Session, 'after_soft_rollback', _after_soft_rollback)
        event.listen(Session, 'do_orm_execute', _do_orm_execute, retval=True)
        _installed = True
