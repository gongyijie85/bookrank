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


class NewBookListQuery(BaseModel):
    """v0.9.63 新增：/api/new-books 列表查询参数。"""

    publisher_id: int | None = Field(default=None, ge=1)
    category: str | None = Field(default=None, max_length=100)
    days: int = Field(default=30, ge=1, le=365)
    search: str = Field(default='', max_length=100)
    page: int = Field(default=1, ge=1, le=10000)
    per_page: int = Field(default=20, ge=1, le=50)


class NewBookSearchQuery(BaseModel):
    """v0.9.63 新增：/api/new-books/search 搜索参数。"""

    keyword: str = Field(min_length=1, max_length=100)
    page: int = Field(default=1, ge=1, le=10000)
    per_page: int = Field(default=20, ge=1, le=50)


class NewBookExportQuery(BaseModel):
    """v0.9.63 新增：/api/new-books/export 导出参数。"""

    publisher_id: int | None = Field(default=None, ge=1)
    category: str | None = Field(default=None, max_length=100)
    days: int = Field(default=30, ge=1, le=365)


class NewBookSyncQuery(BaseModel):
    """v0.9.63 新增：/api/new-books/sync 同步参数。"""

    max_books: int = Field(default=30, ge=1, le=100)


def parse_query_args(model_cls: type[BaseModel], args) -> BaseModel:
    """v0.9.63 新增：把 Flask request.args 解析为 Pydantic 模型。

    字符串字段会自动 strip；空字符串转 None（除 Pydantic 显式标了 default 之外）。
    解析失败抛 ValueError（带人类可读消息），由路由层 catch 转换 422。
    """
    if hasattr(args, 'to_dict'):
        raw: dict[str, str] = {k: (v if v is not None else '') for k, v in args.to_dict(flat=True).items()}
    else:
        raw = {k: ('' if v is None else v) for k, v in dict(args).items()}

    # 字符串字段自动 strip
    for field_name, field in model_cls.model_fields.items():
        if field_name in raw and isinstance(field.annotation, type) and issubclass(field.annotation, str):
            raw[field_name] = raw[field_name].strip()
    return model_cls.model_validate(raw)


class CacheClearRequest(BaseModel):
    older_than_days: int | None = Field(default=None, ge=1)
    min_usage: int | None = Field(default=None, ge=0)
    cache_id: int | None = Field(default=None, ge=1)


class TranslationCacheClearRequest(BaseModel):
    older_than_days: int | None = Field(default=None, ge=1)
    min_usage: int | None = Field(default=None, ge=0)
    cache_id: int | None = Field(default=None, ge=1)
