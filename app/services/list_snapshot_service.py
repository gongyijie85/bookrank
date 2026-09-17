"""榜单快照落库

周报任务本来就会把 13 个 NYT 分类榜全量抓下来，但只留下分析摘要。
本模块把同一批原始条目按周持久化到 list_snapshots，作为排名曲线、
年度榜等历史功能的唯一数据来源。
"""

import logging
from datetime import date
from typing import Any

from ..models.schemas import ListSnapshot, db
from ..utils.error_handler import ErrorCategory, log_error

logger = logging.getLogger(__name__)

# 写入 list_snapshots 的字段白名单；week_start / week_end 由调用参数决定
SNAPSHOT_COLUMNS = (
    'category_id',
    'category_name',
    'book_id',
    'isbn13',
    'isbn10',
    'title',
    'title_zh',
    'author',
    'publisher',
    'cover',
    'original_cover',
    'rank',
    'rank_last_week',
    'rank_change',
    'weeks_on_list',
    'is_new',
    'is_returning',
    'update_frequency',
    'list_published_date',
)


def save_week_snapshot(rows: list[dict[str, Any]], week_start: date, week_end: date) -> int:
    """按周幂等写入快照：同一周重跑先清后写。返回写入行数。

    快照失败不应阻断周报生成，因此这里吞掉数据库异常并记录日志。
    """
    if not rows:
        return 0

    try:
        db.session.query(ListSnapshot).filter(ListSnapshot.week_start == week_start).delete()

        seen: set[tuple[str, str]] = set()
        entities: list[ListSnapshot] = []
        for row in rows:
            category_id = str(row.get('category_id') or '')
            book_id = str(row.get('book_id') or '')
            title = str(row.get('title') or '')
            if not category_id or not book_id or not title:
                continue
            key = (category_id, book_id)
            if key in seen:
                continue
            seen.add(key)
            entities.append(
                ListSnapshot(
                    week_start=week_start,
                    week_end=week_end,
                    **{column: row.get(column) for column in SNAPSHOT_COLUMNS},
                )
            )

        db.session.add_all(entities)
        db.session.commit()
        logger.info('榜单快照已写入 %s 行（week_start=%s）', len(entities), week_start)
        return len(entities)
    except Exception as e:
        log_error(ErrorCategory.DB_QUERY, f'榜单快照写入失败，已回滚: {e}')
        db.session.rollback()
        return 0
