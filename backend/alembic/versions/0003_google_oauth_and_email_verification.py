"""Add Google OAuth external identity, transaction tables, and user email verification fields

Revision ID: 0003_google_oauth_verified_email
Revises: 0002_history_idx_role_check
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_google_oauth_verified_email"
down_revision: Union[str, None] = "0002_history_idx_role_check"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update users table: nullable password_hash, add email_verified & email_verified_at
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=255),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column("email_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False)
        )
        batch_op.add_column(
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
        )

    # 2. Create user_external_identities table
    op.create_table(
        "user_external_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_external_identities_provider_sub"),
    )
    op.create_index(op.f("ix_user_external_identities_id"), "user_external_identities", ["id"], unique=False)
    op.create_index(op.f("ix_user_external_identities_user_id"), "user_external_identities", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_external_identities_provider_user_id"), "user_external_identities", ["provider_user_id"], unique=False)

    # 3. Create oauth_transactions table
    op.create_table(
        "oauth_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("code_verifier_encrypted", sa.String(length=512), nullable=False),
        sa.Column("origin", sa.String(length=255), nullable=False),
        sa.Column("client_challenge", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash", name="uq_oauth_transactions_state_hash"),
    )
    op.create_index(op.f("ix_oauth_transactions_id"), "oauth_transactions", ["id"], unique=False)
    op.create_index(op.f("ix_oauth_transactions_state_hash"), "oauth_transactions", ["state_hash"], unique=True)
    op.create_index(op.f("ix_oauth_transactions_expires_at"), "oauth_transactions", ["expires_at"], unique=False)

    # 4. Create oauth_handoff_tickets table
    op.create_table(
        "oauth_handoff_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_challenge", sa.String(length=128), nullable=False),
        sa.Column("origin", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_hash", name="uq_oauth_handoff_tickets_ticket_hash"),
    )
    op.create_index(op.f("ix_oauth_handoff_tickets_id"), "oauth_handoff_tickets", ["id"], unique=False)
    op.create_index(op.f("ix_oauth_handoff_tickets_ticket_hash"), "oauth_handoff_tickets", ["ticket_hash"], unique=True)
    op.create_index(op.f("ix_oauth_handoff_tickets_user_id"), "oauth_handoff_tickets", ["user_id"], unique=False)
    op.create_index(op.f("ix_oauth_handoff_tickets_expires_at"), "oauth_handoff_tickets", ["expires_at"], unique=False)


def downgrade() -> None:
    # 1. Drop OAuth tables
    op.drop_index(op.f("ix_oauth_handoff_tickets_expires_at"), table_name="oauth_handoff_tickets")
    op.drop_index(op.f("ix_oauth_handoff_tickets_user_id"), table_name="oauth_handoff_tickets")
    op.drop_index(op.f("ix_oauth_handoff_tickets_ticket_hash"), table_name="oauth_handoff_tickets")
    op.drop_index(op.f("ix_oauth_handoff_tickets_id"), table_name="oauth_handoff_tickets")
    op.drop_table("oauth_handoff_tickets")

    op.drop_index(op.f("ix_oauth_transactions_expires_at"), table_name="oauth_transactions")
    op.drop_index(op.f("ix_oauth_transactions_state_hash"), table_name="oauth_transactions")
    op.drop_index(op.f("ix_oauth_transactions_id"), table_name="oauth_transactions")
    op.drop_table("oauth_transactions")

    op.drop_index(op.f("ix_user_external_identities_provider_user_id"), table_name="user_external_identities")
    op.drop_index(op.f("ix_user_external_identities_user_id"), table_name="user_external_identities")
    op.drop_index(op.f("ix_user_external_identities_id"), table_name="user_external_identities")
    op.drop_table("user_external_identities")

    # 2. Revert users table additions
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("email_verified")
        # Note on password_hash: Never delete Google-only accounts or invent dummy passwords.
        # Leave password_hash nullable on downgrade to prevent data loss.
