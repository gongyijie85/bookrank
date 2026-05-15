from pydantic import BaseModel, Field, field_validator


class BookSearchRequest(BaseModel):
    keyword: str = Field(min_length=2, max_length=100)

    @field_validator('keyword')
    @classmethod
    def validate_keyword_format(cls, v: str) -> str:
        import re

        v = v.strip()
        if not re.match(r'^[\w\s\-\u4e00-\u9fff]+$', v):
            raise ValueError('关键词格式无效')
        return v


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    source_lang: str = Field(default='en', pattern=r'^[a-z]{2}(-[A-Z]{2})?$')
    target_lang: str = Field(default='zh', pattern=r'^[a-z]{2}(-[A-Z]{2})?$')
    field_type: str = Field(default='text')


class TranslateBookFieldsRequest(BaseModel):
    title: str = Field(default='')
    description: str = Field(default='')
    details: str = Field(default='')
    source_lang: str = Field(default='en')
    target_lang: str = Field(default='zh')

    @field_validator('title', 'description', 'details')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()

    @field_validator('title', 'description', 'details')
    @classmethod
    def check_at_least_one_not_empty(cls, v: str, info) -> str:
        return v

    def has_any_field(self) -> bool:
        return bool(self.title or self.description or self.details)

    @property
    def total_length(self) -> int:
        return len(self.title) + len(self.description) + len(self.details)


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, le=10000)
    limit: int = Field(default=20, ge=1, le=50)


class AwardBooksQuery(BaseModel):
    award_id: int | None = None
    year: int | None = Field(default=None, ge=1900, le=2100)
    category: str | None = None
    keyword: str | None = Field(default=None, max_length=100)
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=50)


class UserPreferencesUpdate(BaseModel):
    view_mode: str | None = Field(default=None, pattern=r'^(grid|list)$')
    preferred_categories: list[str] | None = None
    last_viewed_isbns: list[str] | None = None

    @field_validator('last_viewed_isbns')
    @classmethod
    def validate_isbns(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        import re

        isbn_pattern = re.compile(r'^\d{10}(\d{3})?$|^\d{3}-\d{1,5}-\d{1,7}-\d{1,7}-\d{1,3}$')
        valid = [isbn for isbn in v if isbn_pattern.match(isbn.replace('-', ''))]
        return valid if valid else None


class RecommendationQuery(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)
    strategy: str = Field(default='personalized')

    @field_validator('strategy')
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in ('personalized', 'similarity', 'smart', 'popular'):
            return 'personalized'
        return v


class SmartSearchQuery(BaseModel):
    keyword: str = Field(default='')
    search_type: str = Field(default='all')
    year: int | None = Field(default=None, ge=1900, le=2100)
    award_id: int | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator('search_type')
    @classmethod
    def validate_search_type(cls, v: str) -> str:
        if v not in ('all', 'title', 'author', 'publisher'):
            return 'all'
        return v


class CacheClearRequest(BaseModel):
    older_than_days: int | None = Field(default=None, ge=1)
    min_usage: int | None = Field(default=None, ge=0)
    cache_id: int | None = Field(default=None, ge=1)


class TranslationCacheClearRequest(BaseModel):
    older_than_days: int | None = Field(default=None, ge=1)
    min_usage: int | None = Field(default=None, ge=0)
    cache_id: int | None = Field(default=None, ge=1)
