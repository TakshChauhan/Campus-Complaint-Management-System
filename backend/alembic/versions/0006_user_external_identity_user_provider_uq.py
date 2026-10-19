"""Add unique constraint on (user_id, provider) to user_external_identities table

Revision ID: 0006_user_external_identity_user_provider_uq
Revises: 0005_email_verification_tokens
Create Date: 2026-10-17 12:00:00.000000

Safe, non-destructive migration ensuring a single CCMS user can have at most one
external identity per provider (e.g. Google), preventing duplicate linking.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_user_external_identity_user_provider_uq"
down_revision: Union[str, None] = "0005_email_verification_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_external_identities") as batch_op:
        batch_op.create_unique_constraint(
            "uq_external_identities_user_provider",
            ["user_id", "provider"],
        )


def downgrade() -> None:
    with op.batch_alter_table("user_external_identities") as batch_op:
        batch_op.drop_constraint(
            "uq_external_identities_user_provider",
            type_="unique",
        )
