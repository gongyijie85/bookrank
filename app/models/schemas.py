from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, asdict

from .database import db


class UserPreference(db.Model):
    """用户偏好设置"""
    __tablename__ = 'user_preferences'
    
    session_id = db.Column(db.String(64), primary_key=True)
    view_mode = db.Column(db.String(20), default='grid')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
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
    )


class UserViewedBook(db.Model):
    """用户浏览过的书籍"""
    __tablename__ = 'user_viewed_books'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), db.ForeignKey('user_preferences.session_id'), nullable=False)
    isbn = db.Column(db.String(13), nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('UserPreference', back_populates='viewed_books')
    
    __table_args__ = (
        db.UniqueConstraint('session_id', 'isbn', name='uix_user_book'),
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
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # 翻译字段
    description_zh = db.Column(db.Text)
    details_zh = db.Column(db.Text)
    translated_at = db.Column(db.DateTime)
    
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'keyword': self.keyword,
            'result_count': self.result_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


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
    buy_links: List[dict]
    isbn13: str
    isbn10: str
    price: str
    # 翻译字段（非持久化，用于前端显示）
    description_zh: str = None
    details_zh: str = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_api_response(cls, book_data: dict, category_id: str, category_name: str, 
                         list_name: str, published_date: str, supplement: dict) -> 'Book':
        """从API响应创建Book对象"""
        isbn = book_data.get('primary_isbn13') or book_data.get('primary_isbn10', '')
        
        # 处理价格
        price_value = book_data.get('price')
        try:
            final_price = str(price_value) if price_value and float(price_value) > 0 else '未知'
        except (ValueError, TypeError):
            final_price = '未知'
        
        # 提取购买链接
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
            cover='',  # 将在后续处理
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
