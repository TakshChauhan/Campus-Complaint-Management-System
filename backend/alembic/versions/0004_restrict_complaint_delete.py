"""Restrict complaint deletion on user deletion to protect complaint audit trail

Revision ID: 0004_restrict_complaint_delete
Revises: 0003_google_oauth_verified_email
Create Date: 2026-10-13 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_restrict_complaint_delete"
down_revision: Union[str, None] = "0003_google_oauth_verified_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update complaints.created_by_id foreign key constraint from CASCADE to RESTRICT
    # This prevents student complaint records from being unintentionally deleted when user accounts are removed.
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table(
            "complaints",
            naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
        ) as batch_op:
            inspector = sa.inspect(bind)
            for fk in inspector.get_foreign_keys("complaints"):
                if "created_by_id" in fk.get("constrained_columns", []):
                    batch_op.drop_constraint(fk.get("name") or "fk_complaints_created_by_id_users", type_="foreignkey")
            batch_op.create_foreign_key(
                "fk_complaints_created_by_id_users",
                "users",
                ["created_by_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    else:
        # PostgreSQL / Supabase
        inspector = sa.inspect(bind)
        fk_name = None
        for fk in inspector.get_foreign_keys("complaints"):
            if "created_by_id" in fk.get("constrained_columns", []):
                fk_name = fk.get("name")
                break
        if fk_name:
            op.drop_constraint(fk_name, "complaints", type_="foreignkey")
        else:
            try:
                op.drop_constraint("complaints_created_by_id_fkey", "complaints", type_="foreignkey")
            except Exception:
                pass
        op.create_foreign_key(
            "fk_complaints_created_by_id_users",
            "complaints",
            "users",
            ["created_by_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table(
            "complaints",
            naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
        ) as batch_op:
            batch_op.drop_constraint("fk_complaints_created_by_id_users", type_="foreignkey")
            batch_op.create_foreign_key(
                "fk_complaints_created_by_id_users",
                "users",
                ["created_by_id"],
                ["id"],
                ondelete="CASCADE",
            )
    else:
        op.drop_constraint("fk_complaints_created_by_id_users", "complaints", type_="foreignkey")
        op.create_foreign_key(
            "complaints_created_by_id_fkey",
            "complaints",
            "users",
            ["created_by_id"],
            ["id"],
            ondelete="CASCADE",
        )
