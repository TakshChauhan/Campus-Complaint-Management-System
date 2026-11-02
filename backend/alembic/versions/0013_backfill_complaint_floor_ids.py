"""Backfill complaint floor IDs from exact legacy location codes.

Revision ID: 0013_backfill_complaint_floor_ids
Revises: 0012_complaint_hmc_audiences
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_backfill_complaint_floor_ids"
down_revision: Union[str, None] = "0012_complaint_hmc_audiences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Map only exact canonical codes; preserve the legacy text columns.
    op.execute(sa.text("""
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
    """))


def downgrade() -> None:
    # Data-only migration: intentionally leave backfilled values unchanged.
    pass
