from datetime import datetime, timezone
from dataclasses import dataclass, asdict

from .database import db


class UserPreference(db.Model):
    """用户偏好设置"""
    __tablename__ = 'user_preferences'
    
    session_id = db.Column(db.String(64), primary_key=True)
    view_mode = db.Column(db.String(20), default='grid')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    categories = db.relationship('UserCategory', back_populates='user', cascade='all, delete-orphan')
    viewed_books = db.relationship('UserViewedBook', back_populates='user', cascade='all, delete-orphan')
    
    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'preferred_categories': [uc.category_id for uc in self.categories],
            'last_viewed_isbns': [uvb.isbn for uvb in self.viewed_books[:5]],
            'view_mode': self.view_mode,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class UserCategory(db.Model):
    """用户关注的分类"""
    __tablename__ = 'user_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), db.ForeignKey('user_preferences.session_id'), nullable=False)
    category_id = db.Column(db.String(50), nullable=False)
    
    user = db.relationship('UserPreference', back_populates='categories')
    
    __table_args__ = (
        db.UniqueConstraint('session_id', 'category_id', name='uix_user_category'),
        db.Index('idx_user_categories_session', 'session_id'),
    )


class UserViewedBook(db.Model):
    """用户浏览过的书籍"""
    __tablename__ = 'user_viewed_books'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), db.ForeignKey('user_preferences.session_id'), nullable=False)
    isbn = db.Column(db.String(13), nullable=False)
    viewed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = db.relationship('UserPreference', back_populates='viewed_books')
    
    __table_args__ = (
        db.UniqueConstraint('session_id', 'isbn', name='uix_user_book'),
        db.Index('idx_user_viewed_session', 'session_id'),
    )


class BookMetadata(db.Model):
    """书籍元数据缓存"""
    __tablename__ = 'book_metadata'
    
    isbn = db.Column(db.String(13), primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    author = db.Column(db.String(300), nullable=False)
    details = db.Column(db.Text)
    page_count = db.Column(db.Integer)
    language = db.Column(db.String(50))
    publication_date = db.Column(db.String(50))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    description_zh = db.Column(db.Text)
    details_zh = db.Column(db.Text)
    translated_at = db.Column(db.DateTime)
    
    __table_args__ = (
        db.Index('idx_book_metadata_title', 'title'),
        db.Index('idx_book_metadata_author', 'author'),
    )
    
    def to_dict(self) -> dict:
        return {
            'isbn': self.isbn,
            'title': self.title,
            'author': self.author,
            'details': self.details,
            'page_count': self.page_count,
            'language': self.language,
            'publication_date': self.publication_date,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'description_zh': self.description_zh,
            'details_zh': self.details_zh,
            'translated_at': self.translated_at.isoformat() if self.translated_at else None
        }


class SearchHistory(db.Model):
    """搜索历史"""
    __tablename__ = 'search_history'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    keyword = db.Column(db.String(200), nullable=False)
    result_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        db.Index('idx_search_history_session', 'session_id'),
        db.Index('idx_search_history_created', 'created_at'),
    )
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'keyword': self.keyword,
            'result_count': self.result_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Award(db.Model):
    """国际图书奖项"""
    __tablename__ = 'awards'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100))
    country = db.Column(db.String(50))
    description = db.Column(db.Text)
    category_count = db.Column(db.Integer, default=1)
    icon_class = db.Column(db.String(50))
    established_year = db.Column(db.Integer)
    award_month = db.Column(db.Integer)
    wikidata_id = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    books = db.relationship('AwardBook', back_populates='award', cascade='all, delete-orphan')
    
    __table_args__ = (
        db.Index('idx_awards_name', 'name'),
    )
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'name_en': self.name_en,
            'country': self.country,
            'description': self.description,
            'category_count': self.category_count,
            'icon_class': self.icon_class,
            'established_year': self.established_year,
            'award_month': self.award_month,
            'wikidata_id': self.wikidata_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class AwardBook(db.Model):
    """获奖图书"""
    __tablename__ = 'award_books'
    
    id = db.Column(db.Integer, primary_key=True)
    award_id = db.Column(db.Integer, db.ForeignKey('awards.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(100))
    rank = db.Column(db.Integer)
    
    title = db.Column(db.String(500), nullable=False)
    title_zh = db.Column(db.String(500))
    author = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    description_zh = db.Column(db.Text)
    
    cover_local_path = db.Column(db.String(255))
    cover_original_url = db.Column(db.String(500))
    
    isbn13 = db.Column(db.String(13))
    isbn10 = db.Column(db.String(10))
    publisher = db.Column(db.String(200))
    publication_year = db.Column(db.Integer)
    
    details = db.Column(db.Text)
    buy_links = db.Column(db.Text)
    
    verification_status = db.Column(db.String(20), default='pending')
    verification_checked_at = db.Column(db.DateTime)
    verification_errors = db.Column(db.Text)
    is_displayable = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    award = db.relationship('Award', back_populates='books')
    
    __table_args__ = (
        db.UniqueConstraint('award_id', 'year', 'category', 'isbn13', name='uix_award_book'),
        db.Index('idx_award_books_award_year', 'award_id', 'year'),
        db.Index('idx_award_books_category', 'category'),
        db.Index('idx_award_books_search', 'title', 'author'),
        db.Index('idx_award_books_displayable', 'is_displayable', 'year'),
        db.Index('idx_award_books_isbn', 'isbn13'),
    )
    
    def to_dict(self, include_zh: bool = True) -> dict:
        data = {
            'id': self.id,
            'award_id': self.award_id,
            'year': self.year,
            'category': self.category,
            'rank': self.rank,
            'title': self.title,
            'author': self.author,
            'description': self.description,
            'cover_local_path': self.cover_local_path,
            'cover_original_url': self.cover_original_url,
            'isbn13': self.isbn13,
            'isbn10': self.isbn10,
            'publisher': self.publisher,
            'publication_year': self.publication_year,
            'verification_status': self.verification_status,
            'is_displayable': self.is_displayable,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_zh:
            data.update({
                'title_zh': self.title_zh,
                'description_zh': self.description_zh
            })
        
        return data


class SystemConfig(db.Model):
    """系统配置表"""
    __tablename__ = 'system_config'
    
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)
    description = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    @classmethod
    def get_value(cls, key: str, default: str | None = None) -> str | None:
        """获取配置值"""
        config = cls.query.get(key)
        return config.value if config else default
    
    @classmethod
    def set_value(cls, key: str, value: str, description: str | None = None) -> 'SystemConfig':
        """设置配置值"""
        config = cls.query.get(key)
        if config:
            config.value = value
        else:
            config = cls(key=key, value=value, description=description)
            db.session.add(config)
        return config


@dataclass
class Book:
    """书籍数据类"""
    id: str
    title: str
    author: str
    publisher: str
    cover: str
    list_name: str
    category_id: str
    category_name: str
    rank: int
    weeks_on_list: int
    rank_last_week: str
    published_date: str
    description: str
    details: str
    publication_dt: str
    page_count: str
    language: str
    buy_links: list[dict]
    isbn13: str
    isbn10: str
    price: str
    description_zh: str | None = None
    details_zh: str | None = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_api_response(
        cls,
        book_data: dict,
        category_id: str,
        category_name: str,
        list_name: str,
        published_date: str,
        supplement: dict
    ) -> 'Book':
        """从API响应创建Book对象"""
        isbn = book_data.get('primary_isbn13') or book_data.get('primary_isbn10', '')
        
        price_value = book_data.get('price')
        try:
            final_price = str(price_value) if price_value and float(price_value) > 0 else '未知'
        except (ValueError, TypeError):
            final_price = '未知'
        
        buy_links = [
            {'name': link.get('name', ''), 'url': link.get('url', '')}
            for link in book_data.get('buy_links', [])
            if link.get('url')
        ]
        
        return cls(
            id=isbn,
            title=book_data.get('title', 'Unknown Title'),
            author=book_data.get('author', 'Unknown Author'),
            publisher=book_data.get('publisher', 'Unknown Publisher'),
            cover='',
            list_name=list_name,
            category_id=category_id,
            category_name=category_name,
            rank=book_data.get('rank', 0),
            weeks_on_list=book_data.get('weeks_on_list', 0),
            rank_last_week=book_data.get('rank_last_week', '无'),
            published_date=published_date,
            description=book_data.get('description', 'No summary available.'),
            details=supplement.get('details', 'No detailed description available.'),
            publication_dt=supplement.get('publication_dt', 'Unknown'),
            page_count=str(supplement.get('page_count', 'Unknown')),
            language=supplement.get('language', 'Unknown'),
            buy_links=buy_links,
            isbn13=book_data.get('primary_isbn13', ''),
            isbn10=book_data.get('primary_isbn10', ''),
            price=final_price
        )
