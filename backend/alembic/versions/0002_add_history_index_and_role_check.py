"""Add composite history index and users role check constraint

Revision ID: 0002_history_index_and_role_check
Revises: 0001_initial_sprint1
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_history_idx_role_check"
down_revision: Union[str, None] = "0001_initial_sprint1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add composite index on complaints (created_by_id, created_at)
    with op.batch_alter_table("complaints") as batch_op:
        batch_op.create_index(
            "ix_complaints_created_by_id_created_at",
            ["created_by_id", "created_at"],
            unique=False,
        )

    # 2. Add named CHECK constraint on users.role restricting to student, staff, admin
    with op.batch_alter_table("users") as batch_op:
        batch_op.create_check_constraint(
            "ck_users_role",
            "role IN ('student', 'staff', 'admin')",
        )


def downgrade() -> None:
    # 1. Drop CHECK constraint on users.role
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_role", type_="check")

    # 2. Drop composite index on complaints
    with op.batch_alter_table("complaints") as batch_op:
        batch_op.drop_index("ix_complaints_created_by_id_created_at")
