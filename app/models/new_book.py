"""
新书速递数据模型

包含出版社和新书两个核心模型，用于管理大型出版社的新书信息。
"""

import json
from datetime import UTC, date, datetime
from typing import Any

from .database import db


class Publisher(db.Model):
    """
    出版社模型

    存储出版社基本信息和爬虫配置。
    支持5大国际出版社：Penguin Random House、Simon & Schuster、
    Hachette、HarperCollins、Macmillan。
    """

    __tablename__ = 'publishers'

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(200), nullable=False, comment='出版社中文名')
    name_en: str = db.Column(db.String(200), nullable=False, index=True, comment='出版社英文名')
    website: str | None = db.Column(db.String(500), comment='官方网站')
    crawler_class: str = db.Column(db.String(100), nullable=False, comment='爬虫类名')
    is_active: bool = db.Column(db.Boolean, default=True, index=True, comment='是否启用爬虫')
    last_sync_at: datetime | None = db.Column(db.DateTime, comment='最后同步时间')
    sync_count: int = db.Column(db.Integer, default=0, comment='同步次数')
    # 官网采集主路径开关与健康状态（#132 预留；默认保持 Google 系现网路径）
    site_crawl_enabled: bool = db.Column(db.Boolean, default=False, nullable=False, comment='是否启用官网采集')
    site_import_enabled: bool = db.Column(db.Boolean, default=False, nullable=False, comment='是否启用批次入库')
    site_display_primary: bool = db.Column(
        db.Boolean, default=False, nullable=False, comment='展示是否以官网批次为主权威'
    )
    fallback_google_enabled: bool = db.Column(
        db.Boolean, default=True, nullable=False, comment='降级时是否启用 Google 兜底'
    )
    source_status: str = db.Column(
        db.String(32), default='healthy', nullable=False, comment='来源健康状态 healthy/degraded/disabled/recovering'
    )
    consecutive_failures: int = db.Column(db.Integer, default=0, nullable=False, comment='连续计划失败次数')
    consecutive_successes: int = db.Column(db.Integer, default=0, nullable=False, comment='连续计划成功次数')
    last_success_batch_id: str | None = db.Column(db.String(128), comment='上次成功导入 batch_id')
    last_attempt_at: datetime | None = db.Column(db.DateTime, comment='上次计划尝试时间')
    last_error_code: str | None = db.Column(db.String(64), comment='最近计划失败机器码')
    last_error_summary: str | None = db.Column(db.String(500), comment='最近计划失败摘要（无密钥无正文）')
    created_at: datetime = db.Column(db.DateTime, default=lambda: datetime.now(UTC), comment='创建时间')
    updated_at: datetime = db.Column(
        db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), comment='更新时间'
    )

    # 关联关系
    books = db.relationship('NewBook', back_populates='publisher', cascade='all, delete-orphan', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('name_en', name='uix_publisher_name_en'),
        db.Index('idx_publisher_active_sync', 'is_active', 'last_sync_at'),
    )

    def to_dict(self, include_book_count: bool = False) -> dict[str, Any]:
        """转换为字典

        Args:
            include_book_count: 是否包含书籍数量（避免N+1查询，默认False）
        """
        data = {
            'id': self.id,
            'name': self.name,
            'name_en': self.name_en,
            'website': self.website,
            'crawler_class': self.crawler_class,
            'is_active': self.is_active,
            'last_sync_at': self.last_sync_at.isoformat() if self.last_sync_at else None,
            'sync_count': self.sync_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_book_count:
            data['books_count'] = self.books.count()
        return data

    def __repr__(self) -> str:
        return f'<Publisher {self.name_en}>'


class NewBook(db.Model):
    """
    新书模型

    存储从出版社网站爬取的新书信息，包括多语言支持。
    """

    __tablename__ = 'new_books'

    id: int = db.Column(db.Integer, primary_key=True)
    publisher_id: int = db.Column(
        db.Integer, db.ForeignKey('publishers.id', ondelete='CASCADE'), nullable=False, index=True, comment='出版社ID'
    )

    # 书籍基本信息
    title: str = db.Column(db.String(500), nullable=False, index=True, comment='原书名')
    title_zh: str | None = db.Column(db.String(500), comment='中文书名')
    author: str = db.Column(db.String(300), nullable=False, index=True, comment='作者')
    description: str | None = db.Column(db.Text, comment='原文简介')
    description_zh: str | None = db.Column(db.Text, comment='中文简介')

    # ISBN 信息
    isbn13: str | None = db.Column(db.String(13), index=True, comment='ISBN-13')
    isbn10: str | None = db.Column(db.String(10), comment='ISBN-10')

    # 封面信息
    cover_url: str | None = db.Column(db.String(500), comment='封面原图URL')
    cover_local: str | None = db.Column(db.String(255), comment='本地缓存封面路径')

    # 出版信息
    category: str | None = db.Column(db.String(100), index=True, comment='分类')
    publication_date: date | None = db.Column(db.Date, comment='出版日期')
    price: str | None = db.Column(db.String(50), comment='价格')
    page_count: int | None = db.Column(db.Integer, comment='页数')
    language: str | None = db.Column(db.String(50), comment='语言')

    # 购买链接（JSON格式存储）
    buy_links: str | None = db.Column(db.Text, comment='购买链接JSON')

    # 来源信息
    source_url: str | None = db.Column(db.String(500), comment='来源页面URL')
    canonical_source_url: str | None = db.Column(db.String(500), comment='规范化官网产品 URL（归并键）')

    # 关联版本与字段出处（JSON 文本；不做全站 Edition 表）
    editions_json: str | None = db.Column(db.Text, comment='关联版本 JSON')
    field_provenance_json: str | None = db.Column(db.Text, comment='字段出处 JSON')
    last_import_batch_id: str | None = db.Column(db.String(128), comment='写入本卡片的上次导入 batch_id')

    # 状态信息
    is_verified: bool = db.Column(db.Boolean, default=False, index=True, comment='是否已验证')
    is_displayable: bool = db.Column(db.Boolean, default=True, index=True, comment='是否可展示')

    # 时间戳
    created_at: datetime = db.Column(db.DateTime, default=lambda: datetime.now(UTC), comment='创建时间')
    updated_at: datetime = db.Column(
        db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), comment='更新时间'
    )

    # 关联关系
    publisher = db.relationship('Publisher', back_populates='books')

    __table_args__ = (
        # 同一出版社下 ISBN 唯一
        db.UniqueConstraint('publisher_id', 'isbn13', name='uix_publisher_isbn13'),
        # 复合索引：出版社 + 出版日期
        db.Index('idx_new_books_publisher_date', 'publisher_id', 'publication_date'),
        # 复合索引：分类 + 可展示
        db.Index('idx_new_books_category_display', 'category', 'is_displayable'),
        # 全文搜索索引
        db.Index('idx_new_books_search', 'title', 'author'),
    )

    # 「刚上市」徽章的判定阈值（天），与新书速递现有「最近7天出版」筛选选项口径一致
    RECENTLY_PUBLISHED_WITHIN_DAYS = 7

    @property
    def is_recently_published(self) -> bool:
        """出版日期是否在最近 N 天内（用于新书速递卡片的"刚上市"徽章）"""
        if not self.publication_date:
            return False
        days_since = (date.today() - self.publication_date).days
        return 0 <= days_since <= self.RECENTLY_PUBLISHED_WITHIN_DAYS

    def to_dict(self, include_zh: bool = True, include_freshness: bool = True) -> dict[str, Any]:
        """转换为字典"""
        from ..utils import quick_clean_translation

        data: dict[str, Any] = {
            'id': self.id,
            'publisher_id': self.publisher_id,
            'publisher_name': self.publisher.name if self.publisher else None,
            'publisher_name_en': ((self.publisher.name_en or self.publisher.name) if self.publisher else None),
            'title': self.title,
            'author': self.author,
            'description': self.description,
            'isbn13': self.isbn13,
            'isbn10': self.isbn10,
            'cover_url': self.cover_url,
            'cover_local': self.cover_local,
            'category': self.category,
            'publication_date': self.publication_date.isoformat() if self.publication_date else None,
            'price': self.price,
            'page_count': self.page_count,
            'language': self.language,
            'buy_links': self.get_buy_links(),
            'source_url': self.source_url,
            'canonical_source_url': self.canonical_source_url,
            'editions': self.get_editions(),
            'field_provenance': self.get_field_provenance(),
            'last_import_batch_id': self.last_import_batch_id,
            'is_verified': self.is_verified,
            'is_displayable': self.is_displayable,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

        if include_freshness:
            data['is_recently_published'] = self.is_recently_published

        if include_zh:
            data.update(
                {
                    'title_zh': quick_clean_translation(self.title_zh, 'title'),
                    'description_zh': quick_clean_translation(self.description_zh, 'description'),
                }
            )

        return data

    def set_buy_links(self, links: list[dict[str, str]]) -> None:
        """设置购买链接"""
        self.buy_links = json.dumps(links, ensure_ascii=False)

    def get_buy_links(self) -> list[dict[str, str]]:
        """获取购买链接；脏数据（非 list / 解析失败）返回空列表。"""
        if not self.buy_links:
            return []
        try:
            raw = json.loads(self.buy_links)
        except (json.JSONDecodeError, TypeError):
            return []
        return raw if isinstance(raw, list) else []

    def set_editions(self, editions: list[dict[str, Any]]) -> None:
        """设置关联版本列表（元素含 format / isbn13 / is_main）。"""
        self.editions_json = json.dumps(editions, ensure_ascii=False)

    def get_editions(self) -> list[dict[str, Any]]:
        """读取关联版本；无数据/脏数据时返回空列表。"""
        if not self.editions_json:
            return []
        try:
            raw = json.loads(self.editions_json)
        except (json.JSONDecodeError, TypeError):
            return []
        return raw if isinstance(raw, list) else []

    def set_field_provenance(self, provenance: list[dict[str, Any]]) -> None:
        """设置字段出处列表。"""
        self.field_provenance_json = json.dumps(provenance, ensure_ascii=False)

    def get_field_provenance(self) -> list[dict[str, Any]]:
        """读取字段出处；无数据/脏数据时返回空列表。"""
        if not self.field_provenance_json:
            return []
        try:
            raw = json.loads(self.field_provenance_json)
        except (json.JSONDecodeError, TypeError):
            return []
        return raw if isinstance(raw, list) else []

    def __repr__(self) -> str:
        return f'<NewBook {self.title} by {self.author}>'


class BatchImportReceipt(db.Model):  # type: ignore[name-defined]
    """采集批次导入回执：支撑 batch_id 幂等与内容冲突检测。"""

    __tablename__ = 'batch_import_receipts'

    batch_id: str = db.Column(db.String(128), primary_key=True)
    content_sha256: str = db.Column(db.String(64), nullable=False)
    source_id: str = db.Column(db.String(64), nullable=False, index=True)
    status: str = db.Column(db.String(32), nullable=False, comment='applied|duplicate|rejected')
    receipt_json: str = db.Column(db.Text, nullable=False)
    created_at: datetime = db.Column(db.DateTime, default=lambda: datetime.now(UTC), nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.receipt_json)
