"""Public-feed publication state, HMC groups, moderators and moderation audit.

Revision ID: 0011_public_feed_hmc
Revises: 0010_complaint_floor_location

Rebased from the PR #46 draft (``0009_public_feed_hmc``) onto the canonical
``hostels -> hostel_wings -> hostel_floors`` hierarchy. The draft's separate
``buildings``/``floors``/``wings`` tables and ``users.residence_*`` columns are
not created: HMC groups map canonical floors, complaints keep the canonical
``floor_id`` from 0010 and residence verification lives in
``student_residences`` from 0009.

Existing complaints are classified conservatively and never exposed through a
guessed HMC mapping. Any public request with a canonical floor, legacy location
text or the Hostel department becomes ``pending_mapping``.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_public_feed_hmc"
down_revision: Union[str, None] = "0010_complaint_floor_location"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


HAS_LOCATION = (
    "(floor_id IS NOT NULL OR trim(coalesce(hostel, '')) <> '' "
    "OR trim(coalesce(wing, '')) <> '' OR trim(coalesce(floor, '')) <> '')"
)
IS_HOSTEL_DEPARTMENT = "department_id IN (SELECT id FROM departments WHERE lower(trim(name)) = 'hostel')"
HMC_SCOPED = f"({HAS_LOCATION} OR {IS_HOSTEL_DEPARTMENT})"

COMPLAINT_CHECKS = (
    (
        "ck_complaints_visibility_scope",
        "visibility_scope IN ('private', 'department_public', 'hmc_group_public')",
    ),
    (
        "ck_complaints_feed_review_status",
        "feed_review_status IN ('not_required', 'pending', 'approved', 'auto_approved', 'rejected')",
    ),
    (
        "ck_complaints_publication_status",
        "publication_status IN ('private', 'pending_review', 'pending_mapping', 'published', 'rejected')",
    ),
    (
        "ck_complaints_public_scope_consistency",
        "(visibility_scope = 'private' AND is_public = false) OR "
        "(visibility_scope IN ('department_public', 'hmc_group_public') AND is_public = true)",
    ),
    (
        "ck_complaints_department_public_no_location",
        "visibility_scope != 'department_public' OR (floor_id IS NULL AND "
        "trim(coalesce(hostel, '')) = '' AND trim(coalesce(wing, '')) = '' AND trim(coalesce(floor, '')) = '')",
    ),
)
INDEXED_COMPLAINT_COLUMNS = ("visibility_scope", "feed_review_status", "publication_status")


def upgrade() -> None:
    op.create_table(
        "hmc_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("hostel_id", sa.Integer(), nullable=False),
        sa.Column("floor_code", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "floor_code = upper(trim(floor_code)) AND length(floor_code) > 0",
            name="ck_hmc_groups_floor_code_canonical",
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_hmc_groups_name_nonempty"),
        sa.ForeignKeyConstraint(["hostel_id"], ["hostels.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_hmc_groups_name"),
    )
    op.create_index("ix_hmc_groups_hostel_id", "hmc_groups", ["hostel_id"])

    op.create_table(
        "hmc_group_floors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hmc_group_id", sa.Integer(), nullable=False),
        sa.Column("floor_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["hmc_group_id"], ["hmc_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["floor_id"], ["hostel_floors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("floor_id", name="uq_hmc_group_floors_floor_id"),
    )
    op.create_index("ix_hmc_group_floors_hmc_group_id", "hmc_group_floors", ["hmc_group_id"])

    op.create_table(
        "hmc_group_moderators",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hmc_group_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["hmc_group_id"], ["hmc_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hmc_group_id", "user_id", name="uq_hmc_group_moderators_group_user"),
    )
    op.create_index("ix_hmc_group_moderators_user_id", "hmc_group_moderators", ["user_id"])

    # Batch mode lets SQLite add the reviewer FK and CHECK constraints as well;
    # PostgreSQL applies the same operations in place.
    with op.batch_alter_table("complaints") as batch_op:
        batch_op.add_column(sa.Column(
            "visibility_scope", sa.String(length=24), server_default=sa.text("'private'"), nullable=False,
        ))
        batch_op.add_column(sa.Column(
            "feed_review_status", sa.String(length=16), server_default=sa.text("'not_required'"), nullable=False,
        ))
        batch_op.add_column(sa.Column(
            "publication_status", sa.String(length=24), server_default=sa.text("'private'"), nullable=False,
        ))
        batch_op.add_column(sa.Column("feed_reviewed_by_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("feed_reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("feed_review_note", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_complaints_feed_reviewed_by_id_users", "users",
            ["feed_reviewed_by_id"], ["id"], ondelete="RESTRICT",
        )
        for column in INDEXED_COMPLAINT_COLUMNS:
            batch_op.create_index(f"ix_complaints_{column}", [column])

    # Preserve every complaint; only non-located, non-Hostel public requests publish.
    op.execute(sa.text(
        "UPDATE complaints SET "
        "visibility_scope = CASE "
        "WHEN is_public = false THEN 'private' "
        f"WHEN {HMC_SCOPED} THEN 'hmc_group_public' "
        "ELSE 'department_public' END, "
        "feed_review_status = CASE "
        f"WHEN is_public = true AND {HMC_SCOPED} THEN 'pending' "
        "ELSE 'not_required' END, "
        "publication_status = CASE "
        "WHEN is_public = false THEN 'private' "
        f"WHEN {HMC_SCOPED} THEN 'pending_mapping' "
        "ELSE 'published' END"
    ))

    with op.batch_alter_table("complaints") as batch_op:
        for name, condition in COMPLAINT_CHECKS:
            batch_op.create_check_constraint(name, condition)

    op.create_table(
        "complaint_publication_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("complaint_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("previous_status", sa.String(length=24), nullable=False),
        sa.Column("new_status", sa.String(length=24), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_complaint_publication_audit_complaint_id", "complaint_publication_audit", ["complaint_id"],
    )
    op.create_index(
        "ix_complaint_publication_audit_actor_user_id", "complaint_publication_audit", ["actor_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_complaint_publication_audit_actor_user_id", table_name="complaint_publication_audit")
    op.drop_index("ix_complaint_publication_audit_complaint_id", table_name="complaint_publication_audit")
    op.drop_table("complaint_publication_audit")

    with op.batch_alter_table("complaints") as batch_op:
        for name, _ in reversed(COMPLAINT_CHECKS):
            batch_op.drop_constraint(name, type_="check")
        for column in reversed(INDEXED_COMPLAINT_COLUMNS):
            batch_op.drop_index(f"ix_complaints_{column}")
        batch_op.drop_constraint("fk_complaints_feed_reviewed_by_id_users", type_="foreignkey")
        for column in (
            "feed_review_note", "feed_reviewed_at", "feed_reviewed_by_id",
            "publication_status", "feed_review_status", "visibility_scope",
        ):
            batch_op.drop_column(column)

    op.drop_index("ix_hmc_group_moderators_user_id", table_name="hmc_group_moderators")
    op.drop_table("hmc_group_moderators")
    op.drop_index("ix_hmc_group_floors_hmc_group_id", table_name="hmc_group_floors")
    op.drop_table("hmc_group_floors")
    op.drop_index("ix_hmc_groups_hostel_id", table_name="hmc_groups")
    op.drop_table("hmc_groups")
