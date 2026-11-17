"""Create complaint comments.

Revision ID: 0015_complaint_comments
Revises: 0014_staff_hostel_assignments
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_complaint_comments"
down_revision: Union[str, None] = "0014_staff_hostel_assignments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "complaint_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complaint_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 1000", name="ck_complaint_comments_body_length"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_complaint_comments_complaint_created_id",
        "complaint_comments",
        ["complaint_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_complaint_comments_complaint_created_id", table_name="complaint_comments")
    op.drop_table("complaint_comments")
