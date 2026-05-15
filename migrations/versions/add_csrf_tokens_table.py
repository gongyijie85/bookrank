"""Add csrf_tokens table

Revision ID: add_csrf_tokens_table
Revises: add_chinese_fields
Create Date: 2026-05-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_csrf_tokens_table'
down_revision = 'add_chinese_fields'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'csrf_tokens',
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('token'),
    )
    with op.batch_alter_table('csrf_tokens', schema=None) as batch_op:
        batch_op.create_index('idx_csrf_tokens_created_at', ['created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('csrf_tokens', schema=None) as batch_op:
        batch_op.drop_index('idx_csrf_tokens_created_at')
    op.drop_table('csrf_tokens')
