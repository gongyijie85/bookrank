"""Add list_snapshots: weekly full-fidelity NYT bestseller snapshots

Revision ID: add_list_snapshots
Revises: add_perf_indexes
Create Date: 2026-09-10 01:30:00.000000

weekly_reports.content 只存分析摘要（top_changes / new_books / longest_running 等
子集），无法回溯任意一周的完整榜单。本表由周报任务写入，保存每周 13 个分类榜的
全量条目，是排名曲线与年度榜的地基。
"""

import sqlalchemy as sa
from alembic import op

revision = 'add_list_snapshots'
down_revision = 'add_perf_indexes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'list_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('week_end', sa.Date(), nullable=False),
        sa.Column('category_id', sa.String(length=64), nullable=False),
        sa.Column('category_name', sa.String(length=100), nullable=True),
        sa.Column('book_id', sa.String(length=64), nullable=False),
        sa.Column('isbn13', sa.String(length=13), nullable=True),
        sa.Column('isbn10', sa.String(length=10), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('title_zh', sa.String(length=500), nullable=True),
        sa.Column('author', sa.String(length=300), nullable=True),
        sa.Column('publisher', sa.String(length=200), nullable=True),
        sa.Column('cover', sa.String(length=500), nullable=True),
        sa.Column('original_cover', sa.String(length=500), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('rank_last_week', sa.String(length=20), nullable=True),
        sa.Column('rank_change', sa.Integer(), nullable=True),
        sa.Column('weeks_on_list', sa.Integer(), nullable=True),
        sa.Column('is_new', sa.Boolean(), nullable=True),
        sa.Column('is_returning', sa.Boolean(), nullable=True),
        sa.Column('update_frequency', sa.String(length=10), nullable=True),
        sa.Column('list_published_date', sa.String(length=20), nullable=True),
        sa.Column('captured_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('week_start', 'category_id', 'book_id', name='uix_list_snapshot_week_category_book'),
    )
    with op.batch_alter_table('list_snapshots', schema=None) as batch_op:
        batch_op.create_index('ix_list_snapshots_week_start', ['week_start'], unique=False)
        batch_op.create_index('idx_list_snapshots_book_week', ['book_id', 'week_start'], unique=False)
        batch_op.create_index('idx_list_snapshots_category_week', ['category_id', 'week_start'], unique=False)


def downgrade():
    with op.batch_alter_table('list_snapshots', schema=None) as batch_op:
        batch_op.drop_index('idx_list_snapshots_category_week')
        batch_op.drop_index('idx_list_snapshots_book_week')
        batch_op.drop_index('ix_list_snapshots_week_start')
    op.drop_table('list_snapshots')
