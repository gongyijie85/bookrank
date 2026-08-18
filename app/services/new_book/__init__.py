"""新书速递子模块的装配点。

对外只暴露 create_new_book_modules() 一个装配接口：把
PublisherManager / TranslationPipeline / SyncEngine / NewBookQueryService
接线为应用级持有对象 NewBookModules，由 app.setup.init_services 注册到
app.extensions['new_book_modules']。各子模块的深度藏在各自模块内，
此处只做接线，不再充当透传门面。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import current_app, has_app_context

from ..book_language_pack import BookLanguagePack
from .publisher_manager import PublisherManager
from .query_service import NewBookQueryService
from .sync_engine import SyncEngine
from .translation_pipeline import TranslationPipeline


@dataclass
class NewBookModules:
    """应用级新书速递子模块持有对象：装配产物，不是门面。"""

    publisher_manager: PublisherManager
    translation_pipeline: TranslationPipeline
    sync_engine: SyncEngine
    query_service: NewBookQueryService


def create_new_book_modules(
    translation_service: Any | None = None,
    language_pack_path: str | Path | None = None,
) -> NewBookModules:
    """装配新书速递子模块并返回持有对象。"""
    language_pack = BookLanguagePack(language_pack_path or _resolve_language_pack_path())
    translation_pipeline = TranslationPipeline(translation_service, language_pack)
    publisher_manager = PublisherManager()
    sync_engine = SyncEngine(publisher_manager, translation_pipeline)
    query_service = NewBookQueryService(translation_pipeline)
    return NewBookModules(
        publisher_manager=publisher_manager,
        translation_pipeline=translation_pipeline,
        sync_engine=sync_engine,
        query_service=query_service,
    )


def _resolve_language_pack_path() -> Path | None:
    if has_app_context() and current_app.static_folder:
        return Path(current_app.static_folder) / 'data' / 'book_language_pack.zh.json'
    return None
