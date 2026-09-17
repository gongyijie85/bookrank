"""Add performance indexes: composite display/date window + GIN trigram search

Revision ID: add_perf_indexes
Revises: merge_20260813_heads
Create Date: 2026-09-04 12:00:00.000000

Performance audit 2026-09-04 (P-HIGH-03 / P-MEDIUM-04):

- ``new_books`` 列表窗口查询 ``is_displayable + publication_date BETWEEN``
  与 ``created_at`` 排序需要复合索引覆盖，避免 seq-scan。
- ``ILIKE '%kw%'`` 前导通配在 btree 索引下无效，需 PostgreSQL
  ``pg_trgm`` GIN；SQLite（本地开发/测试）无法创建，按方言守卫。
"""

import sqlalchemy as sa
from alembic import op

revision = 'add_perf_indexes'
down_revision = 'merge_20260813_heads'
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == 'postgresql'


def upgrade():
    # 1) new_books：窗口排序复合索引（跨 SQLite/PG）
    op.create_index(
        'idx_new_books_display_date',
        'new_books',
        ['is_displayable', 'publication_date'],
        unique=False,
    )
    op.create_index(
        'idx_new_books_display_created',
        'new_books',
        ['is_displayable', 'created_at'],
        unique=False,
    )
    op.create_index(
        'idx_new_books_canonical',
        'new_books',
        ['canonical_source_url'],
        unique=False,
    )

    # 2) award_books：year/category DISTINCT 排序辅助（跨 SQLite/PG）
    op.create_index(
        'idx_award_books_year',
        'award_books',
        ['year'],
        unique=False,
    )

    # 3) PostgreSQL 专属：pg_trgm GIN，加速 ILIKE '%kw%' 搜索
    if _is_postgres():
        op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
        try:
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_new_books_trgm_search "
                "ON new_books USING GIN ("
                "lower(coalesce(title,'')) gin_trgm_ops, "
                "lower(coalesce(title_zh,'')) gin_trgm_ops, "
                "lower(coalesce(author,'')) gin_trgm_ops)"
            )
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_award_books_trgm_search "
                "ON award_books USING GIN ("
                "lower(coalesce(title,'')) gin_trgm_ops, "
                "lower(coalesce(author,'')) gin_trgm_ops, "
                "lower(coalesce(title_zh,'')) gin_trgm_ops)"
            )
        except sa.exc.OperationalError:
            # Supabase 某些实例不允许扩展/索引，失败不阻塞升级
            pass


def downgrade():
    op.drop_index('idx_new_books_canonical', table_name='new_books')
    op.drop_index('idx_new_books_display_created', table_name='new_books')
    op.drop_index('idx_new_books_display_date', table_name='new_books')
    op.drop_index('idx_award_books_year', table_name='award_books')
    if _is_postgres():
        try:
            op.execute('DROP INDEX IF EXISTS idx_new_books_trgm_search')
            op.execute('DROP INDEX IF EXISTS idx_award_books_trgm_search')
        except sa.exc.OperationalError:
            pass
