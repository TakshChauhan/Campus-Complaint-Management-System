"""Public feeds with building-aware residence verification, publication state and moderation audit.

This migration follows the merged 0008 hostel location schema. It adds the
existing building/floor/wing HMC management model without deleting the
physical hostel tables. Do not apply the earlier unmerged 0008 HMC draft.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0009_public_feed_hmc"
down_revision: Union[str, None] = "0008_hostel_locations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.create_table(
        "buildings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_buildings_name"),
    )
    op.create_index("ix_buildings_id", "buildings", ["id"], unique=False)
    op.create_index("ix_buildings_name", "buildings", ["name"], unique=False)

    op.create_table(
        "floors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("building_id", "name", name="uq_floors_building_name"),
    )
    op.create_index("ix_floors_id", "floors", ["id"], unique=False)
    op.create_index("ix_floors_building_id", "floors", ["building_id"], unique=False)
    op.create_index("ix_floors_name", "floors", ["name"], unique=False)

    op.create_table(
        "wings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("building_id", "name", name="uq_wings_building_name"),
    )
    op.create_index("ix_wings_id", "wings", ["id"], unique=False)
    op.create_index("ix_wings_building_id", "wings", ["building_id"], unique=False)
    op.create_index("ix_wings_name", "wings", ["name"], unique=False)

    op.create_table(
        "hmc_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("floor_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["floor_id"], ["floors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_hmc_groups_name"),
    )
    op.create_index("ix_hmc_groups_id", "hmc_groups", ["id"], unique=False)
    op.create_index("ix_hmc_groups_name", "hmc_groups", ["name"], unique=False)
    op.create_index("ix_hmc_groups_building_id", "hmc_groups", ["building_id"], unique=False)
    op.create_index("ix_hmc_groups_floor_id", "hmc_groups", ["floor_id"], unique=False)

    op.create_table(
        "hmc_group_wings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hmc_group_id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("floor_id", sa.Integer(), nullable=False),
        sa.Column("wing_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["hmc_group_id"], ["hmc_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["floor_id"], ["floors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["wing_id"], ["wings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("building_id", "floor_id", "wing_id", name="uq_hmc_group_wings_location"),
        sa.UniqueConstraint("hmc_group_id", "wing_id", name="uq_hmc_group_wings_group_wing"),
    )
    for column in ("id", "hmc_group_id", "building_id", "floor_id", "wing_id"):
        op.create_index(f"ix_hmc_group_wings_{column}", "hmc_group_wings", [column], unique=False)

    # Alter existing tables without rebuilding them on SQLite; these three FK constraints
    # are added on PostgreSQL. Service-level checks and verified assignment guard SQLite tests.
    op.add_column("users", sa.Column("residence_building_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("residence_floor_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("wing_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("residence_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("residence_verified_by_id", sa.Integer(), nullable=True))
    for column in ("residence_building_id", "residence_floor_id", "wing_id"):
        op.create_index(f"ix_users_{column}", "users", [column], unique=False)
    if not is_sqlite:
        op.create_foreign_key("fk_users_residence_building_id_buildings", "users", "buildings", ["residence_building_id"], ["id"], ondelete="SET NULL")
        op.create_foreign_key("fk_users_residence_floor_id_floors", "users", "floors", ["residence_floor_id"], ["id"], ondelete="SET NULL")
        op.create_foreign_key("fk_users_wing_id_wings", "users", "wings", ["wing_id"], ["id"], ondelete="SET NULL")
        op.create_foreign_key("fk_users_residence_verified_by_id_users", "users", "users", ["residence_verified_by_id"], ["id"], ondelete="SET NULL")

    complaint_columns = [
        sa.Column("affected_building_id", sa.Integer(), nullable=True),
        sa.Column("affected_floor_id", sa.Integer(), nullable=True),
        sa.Column("affected_wing_id", sa.Integer(), nullable=True),
        sa.Column("visibility_scope", sa.String(length=24), server_default=sa.text("'private'"), nullable=False),
        sa.Column("feed_review_status", sa.String(length=16), server_default=sa.text("'not_required'"), nullable=False),
        sa.Column("feed_reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("feed_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feed_review_note", sa.Text(), nullable=True),
        sa.Column("publication_status", sa.String(length=24), server_default=sa.text("'private'"), nullable=False),
    ]
    for column in complaint_columns:
        op.add_column("complaints", column)
    for column in ("affected_building_id", "affected_floor_id", "affected_wing_id", "visibility_scope", "feed_review_status", "publication_status"):
        op.create_index(f"ix_complaints_{column}", "complaints", [column], unique=False)
    if not is_sqlite:
        op.create_foreign_key("fk_complaints_affected_building_id_buildings", "complaints", "buildings", ["affected_building_id"], ["id"], ondelete="RESTRICT")
        op.create_foreign_key("fk_complaints_affected_floor_id_floors", "complaints", "floors", ["affected_floor_id"], ["id"], ondelete="RESTRICT")
        op.create_foreign_key("fk_complaints_affected_wing_id_wings", "complaints", "wings", ["affected_wing_id"], ["id"], ondelete="RESTRICT")
        op.create_foreign_key("fk_complaints_feed_reviewed_by_id_users", "complaints", "users", ["feed_reviewed_by_id"], ["id"], ondelete="RESTRICT")

    # Conservative migration: preserve every complaint and never expose legacy, unmapped locations.
    op.execute(sa.text(
        "UPDATE complaints SET visibility_scope = CASE "
        "WHEN is_public = false THEN 'private' "
        "WHEN trim(coalesce(hostel, '')) <> '' OR trim(coalesce(wing, '')) <> '' OR trim(coalesce(floor, '')) <> '' THEN 'hmc_group_public' "
        "ELSE 'department_public' END"
    ))
    op.execute(sa.text(
        "UPDATE complaints SET feed_review_status = CASE "
        "WHEN is_public = true AND (trim(coalesce(hostel, '')) <> '' OR trim(coalesce(wing, '')) <> '' OR trim(coalesce(floor, '')) <> '') THEN 'pending' "
        "ELSE 'not_required' END"
    ))
    op.execute(sa.text(
        "UPDATE complaints SET publication_status = CASE "
        "WHEN is_public = false THEN 'private' "
        "WHEN trim(coalesce(hostel, '')) <> '' OR trim(coalesce(wing, '')) <> '' OR trim(coalesce(floor, '')) <> '' THEN 'pending_mapping' "
        "ELSE 'published' END"
    ))

    if not is_sqlite:
        op.create_check_constraint(
            "ck_complaints_visibility_scope", "complaints",
            "visibility_scope IN ('private', 'department_public', 'hmc_group_public')",
        )
        op.create_check_constraint(
            "ck_complaints_feed_review_status", "complaints",
            "feed_review_status IN ('not_required', 'pending', 'approved', 'auto_approved', 'rejected')",
        )
        op.create_check_constraint(
            "ck_complaints_publication_status", "complaints",
            "publication_status IN ('private', 'pending_review', 'pending_mapping', 'published', 'rejected')",
        )
        op.create_check_constraint(
            "ck_complaints_public_scope_consistency", "complaints",
            "(visibility_scope = 'private' AND is_public = false) OR "
            "(visibility_scope IN ('department_public', 'hmc_group_public') AND is_public = true)",
        )
        op.create_check_constraint(
            "ck_complaints_department_public_no_location", "complaints",
            "visibility_scope != 'department_public' OR "
            "(affected_building_id IS NULL AND affected_floor_id IS NULL AND affected_wing_id IS NULL AND "
            "trim(coalesce(hostel, '')) = '' AND trim(coalesce(wing, '')) = '' AND trim(coalesce(floor, '')) = '')",
        )

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
    for column in ("id", "hmc_group_id", "user_id"):
        op.create_index(f"ix_hmc_group_moderators_{column}", "hmc_group_moderators", [column], unique=False)

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
    op.create_index("ix_complaint_publication_audit_id", "complaint_publication_audit", ["id"], unique=False)
    op.create_index("ix_complaint_publication_audit_complaint_id", "complaint_publication_audit", ["complaint_id"], unique=False)
    op.create_index("ix_complaint_publication_audit_actor_user_id", "complaint_publication_audit", ["actor_user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    if not is_sqlite:
        for name in (
            "ck_complaints_department_public_no_location",
            "ck_complaints_public_scope_consistency",
            "ck_complaints_publication_status",
            "ck_complaints_feed_review_status",
            "ck_complaints_visibility_scope",
        ):
            op.drop_constraint(name, "complaints", type_="check")
        for name in (
            "fk_complaints_feed_reviewed_by_id_users",
            "fk_complaints_affected_wing_id_wings",
            "fk_complaints_affected_floor_id_floors",
            "fk_complaints_affected_building_id_buildings",
            "fk_users_residence_verified_by_id_users",
            "fk_users_wing_id_wings",
            "fk_users_residence_floor_id_floors",
            "fk_users_residence_building_id_buildings",
        ):
            table = "users" if name.startswith("fk_users") else "complaints"
            op.drop_constraint(name, table, type_="foreignkey")

    for name, table in (
        ("ix_complaint_publication_audit_actor_user_id", "complaint_publication_audit"),
        ("ix_complaint_publication_audit_complaint_id", "complaint_publication_audit"),
        ("ix_complaint_publication_audit_id", "complaint_publication_audit"),
    ):
        op.drop_index(name, table_name=table)
    op.drop_table("complaint_publication_audit")
    for name in ("ix_hmc_group_moderators_user_id", "ix_hmc_group_moderators_hmc_group_id", "ix_hmc_group_moderators_id"):
        op.drop_index(name, table_name="hmc_group_moderators")
    op.drop_table("hmc_group_moderators")

    for column in ("publication_status", "feed_review_note", "feed_reviewed_at", "feed_reviewed_by_id", "feed_review_status", "visibility_scope", "affected_wing_id", "affected_floor_id", "affected_building_id"):
        index_name = f"ix_complaints_{column}"
        if column not in ("feed_review_note", "feed_reviewed_at", "feed_reviewed_by_id"):
            op.drop_index(index_name, table_name="complaints")
        op.drop_column("complaints", column)
    for column in ("wing_id", "residence_floor_id", "residence_building_id", "residence_verified_by_id", "residence_verified_at"):
        if column in ("wing_id", "residence_floor_id", "residence_building_id"):
            op.drop_index(f"ix_users_{column}", table_name="users")
        op.drop_column("users", column)

    for column in ("id", "hmc_group_id", "building_id", "floor_id", "wing_id"):
        op.drop_index(f"ix_hmc_group_wings_{column}", table_name="hmc_group_wings")
    op.drop_table("hmc_group_wings")
    for column in ("floor_id", "building_id", "name", "id"):
        op.drop_index(f"ix_hmc_groups_{column}", table_name="hmc_groups")
    op.drop_table("hmc_groups")
    for column in ("name", "building_id", "id"):
        op.drop_index(f"ix_wings_{column}", table_name="wings")
    op.drop_table("wings")
    for column in ("name", "building_id", "id"):
        op.drop_index(f"ix_floors_{column}", table_name="floors")
    op.drop_table("floors")
    for column in ("name", "id"):
        op.drop_index(f"ix_buildings_{column}", table_name="buildings")
    op.drop_table("buildings")
