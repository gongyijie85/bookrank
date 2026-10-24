"""Share plain public metadata within one app, outside writing transactions."""

from collections.abc import Callable
from typing import Any, TypeVar, cast

from flask import current_app, has_app_context

from .detail_cache_invalidation import has_uncommitted_cache_writes

_T = TypeVar('_T')


def cached_public_metadata(key: tuple[Any, ...], loader: Callable[[], _T]) -> _T:  # noqa: UP047 -- Python 3.11 runtime
    cache = current_app.extensions.get('book_detail_cache') if has_app_context() else None
    if cache is None or has_uncommitted_cache_writes():
        return loader()
    return cast('_T', cache.get_or_load(key, loader))
