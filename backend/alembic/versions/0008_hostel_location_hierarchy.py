"""Add the Sprint 3 hostel, wing, and floor hierarchy.

Revision ID: 0008_hostel_locations
Revises: 0007_complaint_lifecycle
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_hostel_locations"
down_revision: Union[str, None] = "0007_complaint_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hostels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="ck_hostels_code_canonical"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_hostels_name_nonempty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_hostels_code"),
    )

    op.create_table(
        "hostel_wings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hostel_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="ck_hostel_wings_code_canonical"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_hostel_wings_name_nonempty"),
        sa.ForeignKeyConstraint(["hostel_id"], ["hostels.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_hostel_wings_code"),
    )
    op.create_index("ix_hostel_wings_hostel_id", "hostel_wings", ["hostel_id"])

    op.create_table(
        "hostel_floors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wing_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="ck_hostel_floors_code_canonical"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_hostel_floors_name_nonempty"),
        sa.ForeignKeyConstraint(["wing_id"], ["hostel_wings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wing_id", "code", name="uq_hostel_floors_wing_code"),
    )
    op.create_index("ix_hostel_floors_wing_id", "hostel_floors", ["wing_id"])


def downgrade() -> None:
    op.drop_index("ix_hostel_floors_wing_id", table_name="hostel_floors")
    op.drop_table("hostel_floors")
    op.drop_index("ix_hostel_wings_hostel_id", table_name="hostel_wings")
    op.drop_table("hostel_wings")
    op.drop_table("hostels")
