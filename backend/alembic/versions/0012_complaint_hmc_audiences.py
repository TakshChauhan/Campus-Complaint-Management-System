"""Explicit HMC audience mappings for published complaints.

Revision ID: 0012_complaint_hmc_audiences
Revises: 0011_public_feed_hmc

A published HMC complaint is visible only to groups with a row here. The
responsible group is recorded on auto-publish or approval; a shared-floor
audience (another group on the same hostel floor level) needs its own audited
moderator decision. 0011 publishes no HMC complaint, so there is nothing to
backfill.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_complaint_hmc_audiences"
down_revision: Union[str, None] = "0011_public_feed_hmc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "complaint_hmc_audiences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complaint_id", sa.Integer(), nullable=False),
        sa.Column("hmc_group_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("decided_by_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "source IN ('responsible_group', 'shared_floor')",
            name="ck_complaint_hmc_audiences_source",
        ),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["hmc_group_id"], ["hmc_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("complaint_id", "hmc_group_id", name="uq_complaint_hmc_audiences_complaint_group"),
    )
    op.create_index("ix_complaint_hmc_audiences_hmc_group_id", "complaint_hmc_audiences", ["hmc_group_id"])


def downgrade() -> None:
    op.drop_index("ix_complaint_hmc_audiences_hmc_group_id", table_name="complaint_hmc_audiences")
    op.drop_table("complaint_hmc_audiences")
