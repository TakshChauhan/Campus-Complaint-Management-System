"""Add email verification required field and dedicated verification tokens table

Revision ID: 0005_email_verification_tokens
Revises: 0004_restrict_complaint_delete
Create Date: 2026-10-16 12:00:00.000000

Compatibility decision:
Legacy accounts created prior to this migration are temporarily exempt by default
(email_verification_required=false, server_default='false') and retain their existing
login behavior without being unexpectedly locked out. They are not thereby proven to
own their email addresses, nor does this migration retroactively assert email verification
for existing users.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_email_verification_tokens"
down_revision: Union[str, None] = "0004_restrict_complaint_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add email_verification_required column to users table with safe default false for existing rows
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "email_verification_required",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            )
        )

    # 2. Create verification_tokens table
    op.create_table(
        "verification_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_verification_tokens_token_hash"),
    )
    op.create_index(op.f("ix_verification_tokens_id"), "verification_tokens", ["id"], unique=False)
    op.create_index(op.f("ix_verification_tokens_user_id"), "verification_tokens", ["user_id"], unique=False)
    op.create_index(op.f("ix_verification_tokens_token_hash"), "verification_tokens", ["token_hash"], unique=True)
    op.create_index(op.f("ix_verification_tokens_expires_at"), "verification_tokens", ["expires_at"], unique=False)


def downgrade() -> None:
    # 1. Drop verification_tokens table and indexes
    op.drop_index(op.f("ix_verification_tokens_expires_at"), table_name="verification_tokens")
    op.drop_index(op.f("ix_verification_tokens_token_hash"), table_name="verification_tokens")
    op.drop_index(op.f("ix_verification_tokens_user_id"), table_name="verification_tokens")
    op.drop_index(op.f("ix_verification_tokens_id"), table_name="verification_tokens")
    op.drop_table("verification_tokens")

    # 2. Revert users table addition
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("email_verification_required")
