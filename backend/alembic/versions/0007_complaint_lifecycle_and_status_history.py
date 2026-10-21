"""Add complaint lifecycle fields and status history

Revision ID: 0007_complaint_lifecycle
Revises: 0006_user_external_identity_user_provider_uq
Create Date: 2026-10-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007_complaint_lifecycle"
down_revision: Union[str, None] = "0006_user_external_identity_user_provider_uq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Recreate the SQLite table because SQLite cannot ADD a column whose
    # server default is CURRENT_TIMESTAMP. PostgreSQL uses normal ALTERs.
    bind = op.get_bind()
    recreate = "always" if bind.dialect.name == "sqlite" else "auto"

    with op.batch_alter_table("complaints", recreate=recreate) as batch_op:
        batch_op.add_column(
            sa.Column("is_public", sa.Boolean(), server_default=sa.text("false"), nullable=False)
        )
        batch_op.add_column(sa.Column("hostel", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("wing", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("floor", sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        )
        batch_op.add_column(sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("reopen_count", sa.Integer(), server_default=sa.text("0"), nullable=False)
        )


    # Existing complaints have no reliable last-update timestamp. Use their
    # creation time as the baseline instead of the migration execution time.
    op.execute(sa.text("UPDATE complaints SET updated_at = created_at"))

    op.create_table(
        "complaint_status_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complaint_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_complaint_status_history_complaint_id"),
        "complaint_status_history",
        ["complaint_id"],
        unique=False,
    )

    # Give complaints that predate this table a first timeline entry.
    # A submitted complaint has not yet changed status, so its creation time
    # and creator are the original event. Other statuses are snapshots because
    # their earlier transitions and actors cannot be reconstructed.
    op.execute(
        sa.text(
            "INSERT INTO complaint_status_history "
            "(complaint_id, from_status, to_status, actor_id, remark, created_at) "
            "SELECT id, NULL, status, created_by_id, "
            "CASE WHEN status = 'submitted' THEN NULL "
            "ELSE 'Status at migration; earlier transitions unavailable' END, "
            "CASE WHEN status = 'submitted' THEN created_at "
            "ELSE CURRENT_TIMESTAMP END "
            "FROM complaints"
        )
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_complaint_status_history_complaint_id"),
        table_name="complaint_status_history",
    )
    op.drop_table("complaint_status_history")

    with op.batch_alter_table("complaints") as batch_op:
        batch_op.drop_column("reopen_count")
        batch_op.drop_column("resolved_at")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("floor")
        batch_op.drop_column("wing")
        batch_op.drop_column("hostel")
        batch_op.drop_column("is_public")
