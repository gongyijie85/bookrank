"""
新书速递数据模型

包含出版社和新书两个核心模型，用于管理大型出版社的新书信息。
"""
from datetime import datetime, timezone, date
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
    created_at: datetime = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        comment='创建时间'
    )
    updated_at: datetime = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment='更新时间'
    )

    # 关联关系
    books = db.relationship(
        'NewBook',
        back_populates='publisher',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )

    __table_args__ = (
        db.UniqueConstraint('name_en', name='uix_publisher_name_en'),
        db.Index('idx_publisher_active_sync', 'is_active', 'last_sync_at'),
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'name_en': self.name_en,
            'website': self.website,
            'crawler_class': self.crawler_class,
            'is_active': self.is_active,
            'last_sync_at': self.last_sync_at.isoformat() if self.last_sync_at else None,
            'sync_count': self.sync_count,
            'books_count': self.books.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

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
        db.Integer,
        db.ForeignKey('publishers.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='出版社ID'
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

    # 状态信息
    is_verified: bool = db.Column(db.Boolean, default=False, index=True, comment='是否已验证')
    is_displayable: bool = db.Column(db.Boolean, default=True, index=True, comment='是否可展示')

    # 时间戳
    created_at: datetime = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        comment='创建时间'
    )
    updated_at: datetime = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment='更新时间'
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

    def to_dict(self, include_zh: bool = True) -> dict[str, Any]:
        """转换为字典"""
        import json

        data: dict[str, Any] = {
            'id': self.id,
            'publisher_id': self.publisher_id,
            'publisher_name': self.publisher.name if self.publisher else None,
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
            'buy_links': json.loads(self.buy_links) if self.buy_links else [],
            'source_url': self.source_url,
            'is_verified': self.is_verified,
            'is_displayable': self.is_displayable,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

        if include_zh:
            data.update({
                'title_zh': self.title_zh,
                'description_zh': self.description_zh,
            })

        return data

    def set_buy_links(self, links: list[dict[str, str]]) -> None:
        """设置购买链接"""
        import json
        self.buy_links = json.dumps(links, ensure_ascii=False)

    def get_buy_links(self) -> list[dict[str, str]]:
        """获取购买链接"""
        import json
        return json.loads(self.buy_links) if self.buy_links else []

    def __repr__(self) -> str:
        return f'<NewBook {self.title} by {self.author}>'
