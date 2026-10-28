"""Add one verifiable hostel residence per student.

Revision ID: 0009_student_residences
Revises: 0008_hostel_locations
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_student_residences"
down_revision: Union[str, None] = "0008_hostel_locations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_residences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("floor_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("verified_by_id", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'verified', 'rejected')",
            name="ck_student_residences_status",
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["floor_id"], ["hostel_floors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", name="uq_student_residences_student_id"),
    )
    op.create_index("ix_student_residences_floor_id", "student_residences", ["floor_id"])
    op.create_index(
        "ix_student_residences_status_submitted_at",
        "student_residences",
        ["status", "submitted_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_student_residences_status_submitted_at", table_name="student_residences")
    op.drop_index("ix_student_residences_floor_id", table_name="student_residences")
    op.drop_table("student_residences")
