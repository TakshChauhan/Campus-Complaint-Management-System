"""Add staff-to-hostel assignments.
Revision ID: 0014_staff_hostel_assignments
Revises: 0013_backfill_complaint_floor_ids
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
revision: str = "0014_staff_hostel_assignments"
down_revision: Union[str, None] = "0013_backfill_complaint_floor_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table("staff_hostel_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("hostel_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["hostel_id"], ["hostels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "hostel_id", name="uq_staff_hostel_assignments_user_hostel"))

def downgrade() -> None:
    op.drop_table("staff_hostel_assignments")
