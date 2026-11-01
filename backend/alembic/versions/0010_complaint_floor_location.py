

"""Add canonical floor location to complaints.

Revision ID: 0010_complaint_floor_location
Revises: 0009_student_residences
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_complaint_floor_location"
down_revision: Union[str, None] = "0009_student_residences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode to add a foreign-key constraint
    # to an existing table.
    with op.batch_alter_table("complaints") as batch_op:
        batch_op.add_column(
            sa.Column("floor_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_complaints_floor_id_hostel_floors",
            "hostel_floors",
            ["floor_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_complaints_floor_id",
            ["floor_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("complaints") as batch_op:
        batch_op.drop_index("ix_complaints_floor_id")
        batch_op.drop_constraint(
            "fk_complaints_floor_id_hostel_floors",
            type_="foreignkey",
        )
        batch_op.drop_column("floor_id")
