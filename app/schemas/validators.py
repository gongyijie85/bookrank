from pydantic import BaseModel, Field


class NewBookListQuery(BaseModel):
    """v0.9.63 新增：/api/new-books 列表查询参数。"""

    publisher_id: int | None = Field(default=None, ge=1)
    category: str | None = Field(default=None, max_length=100)
    # 默认30天：维护者决议（2026-08-07）——出版 30 天内才算"新书"，
    # 全链路（展示/抓取窗口）统一按此标准；前端仍保留更宽选项供手动放宽。
    days: int = Field(default=30, ge=1, le=365)
    search: str = Field(default='', max_length=100)
    page: int = Field(default=1, ge=1, le=10000)
    per_page: int = Field(default=20, ge=1, le=50)


class NewBookSearchQuery(BaseModel):
    """v0.9.63 新增:/api/new-books/search 搜索参数 (v0.9.68 增加可选过滤)。"""

    keyword: str = Field(min_length=1, max_length=100)
    publisher_id: int | None = Field(default=None, ge=1)
    category: str | None = Field(default=None, max_length=100)
    # 默认不限时间：按关键词/ISBN找特定一本书时，不应该因为它不够"新"就被过滤掉。
    days: int | None = Field(default=None, ge=1, le=365)
    page: int = Field(default=1, ge=1, le=10000)
    per_page: int = Field(default=20, ge=1, le=50)


class NewBookExportQuery(BaseModel):
    """v0.9.63 新增：/api/new-books/export 导出参数。"""

    publisher_id: int | None = Field(default=None, ge=1)
    category: str | None = Field(default=None, max_length=100)
    # 默认30天：导出常用于"本月新书"报表场景，窗口比列表页默认更窄。
    # 与列表/搜索接口的默认值不同是刻意的，不要为了"统一"而改这三个默认值。
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
