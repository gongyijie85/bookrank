"""Merge the production Alembic heads.

Revision ID: merge_20260813_heads
Revises: create_all_missing_tables, add_pub_last_error
Create Date: 2026-08-13 08:30:00.000000

This revision intentionally has no schema operations.  It joins the legacy
table-creation branch and the new-books/source-health branch so that
``flask db upgrade`` has one unambiguous target in production.
"""

# revision identifiers, used by Alembic.
revision = "merge_20260813_heads"
down_revision = ("create_all_missing_tables", "add_pub_last_error")
branch_labels = None
depends_on = None


def upgrade():
    """Join the two migration branches without changing the schema."""


def downgrade():
    """Restore the two independent migration heads."""

