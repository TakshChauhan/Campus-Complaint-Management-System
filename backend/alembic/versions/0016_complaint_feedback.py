"""Create complaint feedback.

Revision ID: 0016_complaint_feedback
Revises: 0015_complaint_comments
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_complaint_feedback"
down_revision: Union[str, None] = "0015_complaint_comments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "complaint_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complaint_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_complaint_feedback_rating"),
        sa.CheckConstraint("comment IS NULL OR length(comment) <= 500", name="ck_complaint_feedback_comment_length"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("complaint_id", name="uq_complaint_feedback_complaint_id"),
    )


def downgrade() -> None:
    op.drop_table("complaint_feedback")
