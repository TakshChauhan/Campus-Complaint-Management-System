"""Link complaints to canonical hostel floors without losing legacy text.

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


def _backfill_exact_canonical_codes() -> None:
    """Set ``floor_id`` only when all legacy values equal canonical codes.

    Legacy location text remains untouched. Rows with missing, descriptive, or
    ambiguous values intentionally retain ``NULL`` so HMC can map them later.
    """
    op.execute(
        sa.text(
            """
            UPDATE complaints
            SET floor_id = (
                SELECT hostel_floors.id
                FROM hostel_floors
                JOIN hostel_wings ON hostel_wings.id = hostel_floors.wing_id
                JOIN hostels ON hostels.id = hostel_wings.hostel_id
                WHERE hostels.code = upper(trim(complaints.hostel))
                  AND hostel_wings.code = upper(trim(complaints.wing))
                  AND hostel_floors.code = upper(trim(complaints.floor))
            )
            WHERE floor_id IS NULL
              AND hostel IS NOT NULL
              AND wing IS NOT NULL
              AND floor IS NOT NULL
              AND EXISTS (
                SELECT 1
                FROM hostel_floors
                JOIN hostel_wings ON hostel_wings.id = hostel_floors.wing_id
                JOIN hostels ON hostels.id = hostel_wings.hostel_id
                WHERE hostels.code = upper(trim(complaints.hostel))
                  AND hostel_wings.code = upper(trim(complaints.wing))
                  AND hostel_floors.code = upper(trim(complaints.floor))
              )
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    recreate = "always" if bind.dialect.name == "sqlite" else "auto"

    with op.batch_alter_table("complaints", recreate=recreate) as batch_op:
        batch_op.add_column(sa.Column("floor_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_complaints_floor_id_hostel_floors",
            "hostel_floors",
            ["floor_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index("ix_complaints_floor_id", "complaints", ["floor_id"])
    _backfill_exact_canonical_codes()


def downgrade() -> None:
    op.drop_index("ix_complaints_floor_id", table_name="complaints")
    bind = op.get_bind()
    recreate = "always" if bind.dialect.name == "sqlite" else "auto"
    with op.batch_alter_table("complaints", recreate=recreate) as batch_op:
        batch_op.drop_constraint("fk_complaints_floor_id_hostel_floors", type_="foreignkey")
        batch_op.drop_column("floor_id")
