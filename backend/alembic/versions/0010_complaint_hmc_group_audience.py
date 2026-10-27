"""Persist explicit HMC-group audiences for shared-floor complaints."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_complaint_hmc_group_audience"
down_revision: Union[str, None] = "0009_public_feed_hmc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "complaint_hmc_group_audiences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complaint_id", sa.Integer(), nullable=False),
        sa.Column("hmc_group_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hmc_group_id"], ["hmc_groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "complaint_id", "hmc_group_id",
            name="uq_complaint_hmc_group_audiences_complaint_group",
        ),
    )
    op.create_index("ix_complaint_hmc_group_audiences_id", "complaint_hmc_group_audiences", ["id"])
    op.create_index("ix_complaint_hmc_group_audiences_complaint_id", "complaint_hmc_group_audiences", ["complaint_id"])
    op.create_index("ix_complaint_hmc_group_audiences_hmc_group_id", "complaint_hmc_group_audiences", ["hmc_group_id"])


def downgrade() -> None:
    op.drop_index("ix_complaint_hmc_group_audiences_hmc_group_id", table_name="complaint_hmc_group_audiences")
    op.drop_index("ix_complaint_hmc_group_audiences_complaint_id", table_name="complaint_hmc_group_audiences")
    op.drop_index("ix_complaint_hmc_group_audiences_id", table_name="complaint_hmc_group_audiences")
    op.drop_table("complaint_hmc_group_audiences")
