"""Building-aware public-feed visibility, verified residence, and HMC moderation rules."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import Session, joinedload

from app.models.building import Building
from app.models.complaint import Complaint
from app.models.complaint_publication_audit import ComplaintPublicationAudit
from app.models.complaint_hmc_group_audience import ComplaintHMCGroupAudience
from app.models.department import Department
from app.models.floor import Floor
from app.models.hmc_group import HMCGroup, HMCGroupWing
from app.models.hmc_group_moderator import HMCGroupModerator
from app.models.user import User
from app.models.wing import Wing
from app.schemas.complaint import ComplaintCreate
from app.schemas.public_feed import (
    FeedBuildingOption, FeedComplaintDetail, FeedComplaintItem, FeedFloorOption,
    FeedLocationCatalogue, FeedReviewQueueItem, FeedReviewRequest, FeedReviewResult,
    FeedWingOption,
)

SCOPE_PRIVATE = "private"
SCOPE_DEPARTMENT_PUBLIC = "department_public"
SCOPE_HMC_GROUP_PUBLIC = "hmc_group_public"
REVIEW_NOT_REQUIRED = "not_required"
REVIEW_PENDING = "pending"
REVIEW_APPROVED = "approved"
REVIEW_AUTO_APPROVED = "auto_approved"
REVIEW_REJECTED = "rejected"
PUBLICATION_PRIVATE = "private"
PUBLICATION_PENDING_REVIEW = "pending_review"
PUBLICATION_PENDING_MAPPING = "pending_mapping"
PUBLICATION_PUBLISHED = "published"
PUBLICATION_REJECTED = "rejected"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.strip().split())
    return value or None


def _match_named(db: Session, model, value: str | None, *, building_id: int | None = None):
    value = _clean(value)
    if not value:
        return None
    query = db.query(model).filter(func.lower(model.name) == value.lower())
    if building_id is not None and hasattr(model, "building_id"):
        query = query.filter(model.building_id == building_id)
    matches = query.all()
    return matches[0] if len(matches) == 1 else None


def resolve_complaint_location(db: Session, payload: ComplaintCreate) -> dict[str, Any]:
    """Resolve a submitted location; ambiguity fails closed but never blocks complaint creation.

    Building and floor are independent physical dimensions. A wing belongs to a building
    and may be served by different HMC groups on different floors. Student-submitted text
    is never treated as verified residence or authorization.
    """
    requested = any((payload.affected_building_id, payload.affected_floor_id, payload.affected_wing_id,
                     _clean(payload.hostel), _clean(payload.floor), _clean(payload.wing)))
    if not requested:
        return {
            "affected_building_id": None, "affected_floor_id": None, "affected_wing_id": None,
            "hostel": None, "floor": None, "wing": None,
            "is_location_specific": False, "mapping_resolved": True,
        }

    building = db.query(Building).filter(
        Building.id == payload.affected_building_id, Building.is_active.is_(True)
    ).first() if payload.affected_building_id is not None else None
    floor = db.query(Floor).filter(
        Floor.id == payload.affected_floor_id, Floor.is_active.is_(True)
    ).first() if payload.affected_floor_id is not None else None
    wing = db.query(Wing).filter(
        Wing.id == payload.affected_wing_id, Wing.is_active.is_(True)
    ).first() if payload.affected_wing_id is not None else None

    # Invalid/inactive IDs are not silently replaced by free-text labels.
    if (
        (payload.affected_building_id is not None and building is None)
        or (payload.affected_floor_id is not None and floor is None)
        or (payload.affected_wing_id is not None and wing is None)
    ):
        return {
            "affected_building_id": None, "affected_floor_id": None, "affected_wing_id": None,
            "hostel": _clean(payload.hostel), "floor": _clean(payload.floor), "wing": _clean(payload.wing),
            "is_location_specific": True, "mapping_resolved": False,
        }

    # A supplied building label is an explicit assertion. If it cannot be resolved,
    # do not infer a different building from globally unique floor/wing names.
    if building is None and _clean(payload.hostel):
        building = _match_named(db, Building, payload.hostel)
        if building is None:
            return {
                "affected_building_id": None, "affected_floor_id": None, "affected_wing_id": None,
                "hostel": _clean(payload.hostel), "floor": _clean(payload.floor), "wing": _clean(payload.wing),
                "is_location_specific": True, "mapping_resolved": False,
            }
    if floor is None and _clean(payload.floor):
        floor = _match_named(db, Floor, payload.floor, building_id=building.id if building else None)
    if wing is None and _clean(payload.wing):
        wing = _match_named(db, Wing, payload.wing, building_id=building.id if building else None)

    inferred_building_ids = {x for x in (
        building.id if building else None,
        floor.building_id if floor else None,
        wing.building_id if wing else None,
    ) if x is not None}
    if len(inferred_building_ids) == 1 and building is None:
        building = db.query(Building).filter(Building.id == next(iter(inferred_building_ids)), Building.is_active.is_(True)).first()
    consistent = (
        building is not None
        and len(inferred_building_ids) <= 1
        and (floor is None or floor.building_id == building.id)
        and (wing is None or wing.building_id == building.id)
        and (floor is not None)  # wing-only location is ambiguous because a wing spans multiple floors
        and (not _clean(payload.hostel) or _clean(payload.hostel).casefold() == building.name.casefold())
        and (not _clean(payload.floor) or (floor is not None and _clean(payload.floor).casefold() == floor.name.casefold()))
        and (not _clean(payload.wing) or (wing is not None and _clean(payload.wing).casefold() == wing.name.casefold()))
    )
    if wing is not None and floor is not None:
        consistent = bool(consistent and wing.building_id == floor.building_id)
    if floor is None:
        consistent = False

    if not consistent:
        return {
            "affected_building_id": None, "affected_floor_id": None, "affected_wing_id": None,
            "hostel": building.name if building else _clean(payload.hostel),
            "floor": floor.name if floor else _clean(payload.floor),
            "wing": wing.name if wing else _clean(payload.wing),
            "is_location_specific": True, "mapping_resolved": False,
        }
    if building is None or floor is None or not building.is_active or not floor.is_active:
        return {
            "affected_building_id": None, "affected_floor_id": None, "affected_wing_id": None,
            "hostel": _clean(payload.hostel), "floor": _clean(payload.floor), "wing": _clean(payload.wing),
            "is_location_specific": True, "mapping_resolved": False,
        }
    return {
        "affected_building_id": building.id,
        "affected_floor_id": floor.id,
        "affected_wing_id": wing.id if wing else None,
        "hostel": building.name,
        "floor": floor.name,
        "wing": wing.name if wing else None,
        "is_location_specific": True,
        "mapping_resolved": True,
    }


def _group_for_location(db: Session, building_id: int | None, floor_id: int | None, wing_id: int | None = None) -> HMCGroup | None:
    if building_id is None or floor_id is None:
        return None
    q = db.query(HMCGroup).join(HMCGroupWing, HMCGroupWing.hmc_group_id == HMCGroup.id).filter(
        HMCGroup.building_id == building_id,
        HMCGroup.floor_id == floor_id,
        HMCGroup.is_active.is_(True),
        HMCGroupWing.building_id == building_id,
        HMCGroupWing.floor_id == floor_id,
    )
    if wing_id is not None:
        q = q.filter(HMCGroupWing.wing_id == wing_id)
    groups = {group.id: group for group in q.all() if _valid_hmc_group(db, group)}
    return next(iter(groups.values())) if len(groups) == 1 else None


def _valid_hmc_group(db: Session, group: HMCGroup) -> bool:
    building = db.query(Building).filter(Building.id == group.building_id, Building.is_active.is_(True)).first()
    floor = db.query(Floor).filter(
        Floor.id == group.floor_id, Floor.building_id == group.building_id, Floor.is_active.is_(True)
    ).first()
    if building is None or floor is None or not group.is_active:
        return False
    rows = db.query(HMCGroupWing, Wing).join(Wing, Wing.id == HMCGroupWing.wing_id).filter(
        HMCGroupWing.hmc_group_id == group.id
    ).all()
    return bool(1 <= len(rows) <= 2) and all(
        mapping.building_id == group.building_id
        and mapping.floor_id == group.floor_id
        and wing.building_id == group.building_id
        and wing.is_active
        for mapping, wing in rows
    )


def _verified_residence(db: Session, student: User) -> tuple[Building, Floor, Wing] | None:
    if not all((student.residence_building_id, student.residence_floor_id, student.wing_id,
                student.residence_verified_at, student.residence_verified_by_id)):
        return None
    verifier = db.query(User).filter(
        User.id == student.residence_verified_by_id,
        User.role.in_(["staff", "admin"]), User.is_active.is_(True),
    ).first()
    building = db.query(Building).filter(Building.id == student.residence_building_id, Building.is_active.is_(True)).first()
    floor = db.query(Floor).filter(
        Floor.id == student.residence_floor_id,
        Floor.building_id == student.residence_building_id,
        Floor.is_active.is_(True),
    ).first()
    wing = db.query(Wing).filter(
        Wing.id == student.wing_id,
        Wing.building_id == student.residence_building_id,
        Wing.is_active.is_(True),
    ).first()
    if verifier is None or building is None or floor is None or wing is None:
        return None
    return building, floor, wing


def _reporter_matches_hmc_location(db: Session, student: User, location: dict[str, Any]) -> bool:
    residence = _verified_residence(db, student)
    if residence is None or not location.get("mapping_resolved"):
        return False
    building, floor, wing = residence
    if building.id != location.get("affected_building_id") or floor.id != location.get("affected_floor_id"):
        return False
    resident_group = _group_for_location(db, building.id, floor.id, wing.id)
    if resident_group is None:
        return False
    affected_wing_id = location.get("affected_wing_id")
    if affected_wing_id is not None:
        affected_group = _group_for_location(db, building.id, floor.id, affected_wing_id)
        return affected_group is not None and affected_group.id == resident_group.id
    # A missing wing can represent a shared-floor complaint. It must not be
    # auto-published to every group on that floor; a reviewer must select
    # the exact audience groups explicitly.
    return False


def _location_has_valid_hmc_mapping(db: Session, location: dict[str, Any]) -> bool:
    """Return true only when the physical location maps unambiguously to active HMC group(s)."""
    if not location.get("mapping_resolved"):
        return False
    building_id = location.get("affected_building_id")
    floor_id = location.get("affected_floor_id")
    if building_id is None or floor_id is None:
        return False
    if location.get("affected_wing_id") is not None:
        return _group_for_location(
            db, building_id, floor_id, location.get("affected_wing_id")
        ) is not None
    # A shared-floor audience cannot be inferred from co-located groups.
    # It remains unresolved until an authorized reviewer selects audience IDs.
    return False


def classify_complaint_visibility(db: Session, student: User, is_public: bool, location: dict[str, Any],
                                  *, is_hostel: bool = False) -> tuple[str, str, str]:
    """Return legacy scope, legacy review state, and canonical publication status."""
    if not is_public:
        return SCOPE_PRIVATE, REVIEW_NOT_REQUIRED, PUBLICATION_PRIVATE
    # A public Hostel complaint without a mapped location must never become campus-wide.
    if is_hostel and not location.get("is_location_specific"):
        return SCOPE_HMC_GROUP_PUBLIC, REVIEW_PENDING, PUBLICATION_PENDING_MAPPING
    if not location.get("is_location_specific"):
        return SCOPE_DEPARTMENT_PUBLIC, REVIEW_NOT_REQUIRED, PUBLICATION_PUBLISHED
    if not location.get("mapping_resolved") or not _location_has_valid_hmc_mapping(db, location):
        return SCOPE_HMC_GROUP_PUBLIC, REVIEW_PENDING, PUBLICATION_PENDING_MAPPING
    if _reporter_matches_hmc_location(db, student, location):
        return SCOPE_HMC_GROUP_PUBLIC, REVIEW_AUTO_APPROVED, PUBLICATION_PUBLISHED
    return SCOPE_HMC_GROUP_PUBLIC, REVIEW_PENDING, PUBLICATION_PENDING_REVIEW


def _feed_item(complaint: Complaint) -> FeedComplaintItem:
    """Student projection intentionally contains no description, reporter or review fields."""
    building = complaint.affected_building
    return FeedComplaintItem(
        id=complaint.id, title=complaint.title,
        department_id=complaint.department_id,
        department_name=complaint.department.name if complaint.department else "Unknown",
        status=complaint.status,
        affected_building_id=complaint.affected_building_id,
        affected_building_name=building.name if building else None,
        affected_floor_id=complaint.affected_floor_id,
        affected_floor_name=complaint.affected_floor.name if complaint.affected_floor else None,
        affected_wing_id=complaint.affected_wing_id,
        affected_wing_name=complaint.affected_wing.name if complaint.affected_wing else None,
        created_at=complaint.created_at, updated_at=complaint.updated_at,
        resolved_at=complaint.resolved_at,
    )


def _with_feed_relations(query):
    return query.options(
        joinedload(Complaint.department), joinedload(Complaint.affected_building),
        joinedload(Complaint.affected_floor), joinedload(Complaint.affected_wing),
    )


def _limited(query, limit: int, offset: int):
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    total = query.order_by(None).count()
    items = query.order_by(Complaint.created_at.desc(), Complaint.id.desc()).offset(offset).limit(limit).all()
    return [_feed_item(item) for item in items], total


def list_feed_locations(db: Session) -> FeedLocationCatalogue:
    """Return building/floor/wing choices mapped to valid active HMC groups."""
    mappings = db.query(HMCGroupWing, HMCGroup, Building, Floor, Wing).join(
        HMCGroup, HMCGroup.id == HMCGroupWing.hmc_group_id
    ).join(Building, Building.id == HMCGroupWing.building_id).join(
        Floor, Floor.id == HMCGroupWing.floor_id
    ).join(Wing, Wing.id == HMCGroupWing.wing_id).filter(
        HMCGroup.is_active.is_(True), Building.is_active.is_(True),
        Floor.is_active.is_(True), Wing.is_active.is_(True),
    ).all()
    valid = [(mapping, group, building, floor, wing) for mapping, group, building, floor, wing in mappings
             if group.building_id == building.id and group.floor_id == floor.id
             and floor.building_id == building.id and wing.building_id == building.id
             and _valid_hmc_group(db, group)]
    buildings = {b.id: FeedBuildingOption(id=b.id, name=b.name) for _, _, b, _, _ in valid}
    floors = {(b.id, f.id): FeedFloorOption(id=f.id, building_id=b.id, building_name=b.name, name=f.name)
              for _, _, b, f, _ in valid}
    wings = {(b.id, f.id, w.id): FeedWingOption(id=w.id, building_id=b.id, building_name=b.name,
              name=w.name, floor_id=f.id, floor_name=f.name) for _, _, b, f, w in valid}
    return FeedLocationCatalogue(
        buildings=sorted(buildings.values(), key=lambda x: x.name.casefold()),
        floors=sorted(floors.values(), key=lambda x: (x.building_name.casefold(), x.name.casefold())),
        wings=sorted(wings.values(), key=lambda x: (x.building_name.casefold(), x.floor_name.casefold(), x.name.casefold())),
    )


def list_department_public_feed(db: Session, *, department_id: int, status_filter: str | None = None,
                                limit: int = 50, offset: int = 0):
    department = db.query(Department).filter(Department.id == department_id, Department.is_active.is_(True)).first()
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found.")
    if department.name.strip().casefold() == "hostel":
        raise HTTPException(status_code=400, detail={
            "code": "hostel_feed_required",
            "message": "Use the restricted hostel feed for Hostel complaints.",
        })
    query = _with_feed_relations(db.query(Complaint)).filter(
        Complaint.department_id == department_id, Complaint.is_public.is_(True),
        Complaint.visibility_scope == SCOPE_DEPARTMENT_PUBLIC,
        Complaint.publication_status == PUBLICATION_PUBLISHED,
        Complaint.affected_building_id.is_(None), Complaint.affected_floor_id.is_(None),
        Complaint.affected_wing_id.is_(None),
        func.trim(func.coalesce(Complaint.hostel, "")) == "",
        func.trim(func.coalesce(Complaint.wing, "")) == "",
        func.trim(func.coalesce(Complaint.floor, "")) == "",
    )
    if status_filter:
        query = query.filter(Complaint.status == status_filter)
    return _limited(query, limit, offset)


def _student_hmc_group(db: Session, student: User) -> HMCGroup:
    residence = _verified_residence(db, student)
    if residence is None:
        raise HTTPException(status_code=403, detail="Your current building, floor and wing residence is not staff-verified. Contact the campus administrator.")
    building, floor, wing = residence
    group = _group_for_location(db, building.id, floor.id, wing.id)
    if group is None:
        raise HTTPException(status_code=403, detail="Your verified residence has no valid HMC group mapping.")
    return group


def list_student_hmc_feed(db: Session, student: User, *, status_filter: str | None = None,
                          limit: int = 50, offset: int = 0):
    group = _student_hmc_group(db, student)
    wing_ids = [row.wing_id for row in db.query(HMCGroupWing).filter(
        HMCGroupWing.hmc_group_id == group.id,
        HMCGroupWing.building_id == group.building_id,
        HMCGroupWing.floor_id == group.floor_id,
    ).all()]
    if not (1 <= len(wing_ids) <= 2) or not _valid_hmc_group(db, group):
        raise HTTPException(status_code=403, detail="The HMC group mapping is invalid.")
    query = _with_feed_relations(db.query(Complaint)).join(
        Department, Department.id == Complaint.department_id
    ).filter(
        Complaint.is_public.is_(True), Complaint.visibility_scope == SCOPE_HMC_GROUP_PUBLIC,
        Complaint.publication_status == PUBLICATION_PUBLISHED,
        Complaint.feed_review_status.in_([REVIEW_APPROVED, REVIEW_AUTO_APPROVED]),
        Complaint.affected_building_id == group.building_id,
        Complaint.affected_floor_id == group.floor_id,
        Department.is_active.is_(True),
        or_(
            Complaint.affected_wing_id.in_(wing_ids),
            Complaint.id.in_(
                db.query(ComplaintHMCGroupAudience.complaint_id).filter(
                    ComplaintHMCGroupAudience.hmc_group_id == group.id
                )
            ),
        ),
    )
    if status_filter:
        query = query.filter(Complaint.status == status_filter)
    return _limited(query, limit, offset)


def get_accessible_feed_complaint_detail(db: Session, student: User, complaint_id: int) -> FeedComplaintDetail:
    """Return only safe summary metadata, never the complaint description."""
    complaint = _with_feed_relations(db.query(Complaint)).join(
        Department, Department.id == Complaint.department_id
    ).filter(Complaint.id == complaint_id, Department.is_active.is_(True)).first()
    if complaint is None or not complaint.is_public or complaint.publication_status != PUBLICATION_PUBLISHED:
        raise HTTPException(status_code=404, detail="Feed complaint not found.")
    allowed = (
        complaint.visibility_scope == SCOPE_DEPARTMENT_PUBLIC
        and complaint.department.name.strip().casefold() != "hostel"
        and not any(_clean(value) for value in (complaint.hostel, complaint.wing, complaint.floor))
        and complaint.affected_building_id is None
        and complaint.affected_floor_id is None
        and complaint.affected_wing_id is None
    )
    if complaint.visibility_scope == SCOPE_HMC_GROUP_PUBLIC:
        try:
            group = _student_hmc_group(db, student)
        except HTTPException:
            group = None
        if group and complaint.affected_building_id == group.building_id and complaint.affected_floor_id == group.floor_id:
            if complaint.affected_wing_id is None:
                # Shared-floor complaints require an explicit audience mapping.
                allowed = db.query(ComplaintHMCGroupAudience.id).filter(
                    ComplaintHMCGroupAudience.complaint_id == complaint.id,
                    ComplaintHMCGroupAudience.hmc_group_id == group.id,
                ).first() is not None
            else:
                allowed = db.query(HMCGroupWing.id).filter(
                    HMCGroupWing.hmc_group_id == group.id,
                    HMCGroupWing.wing_id == complaint.affected_wing_id,
                    HMCGroupWing.building_id == group.building_id,
                    HMCGroupWing.floor_id == group.floor_id,
                ).first() is not None
    if not allowed:
        raise HTTPException(status_code=404, detail="Feed complaint not found.")
    return FeedComplaintDetail(**_feed_item(complaint).model_dump())


def _group_ids_for_complaint(db: Session, complaint: Complaint) -> set[int]:
    if complaint.affected_building_id is None or complaint.affected_floor_id is None:
        return set()
    if complaint.affected_wing_id is None:
        # Never infer all groups on a floor as the audience. Only persisted,
        # explicitly selected group IDs count as authorized scope.
        return {row.hmc_group_id for row in db.query(ComplaintHMCGroupAudience).filter(
            ComplaintHMCGroupAudience.complaint_id == complaint.id
        ).all()}
    q = db.query(HMCGroup).filter(
        HMCGroup.building_id == complaint.affected_building_id,
        HMCGroup.floor_id == complaint.affected_floor_id, HMCGroup.is_active.is_(True),
    )
    if complaint.affected_wing_id is not None:
        q = q.join(HMCGroupWing, HMCGroupWing.hmc_group_id == HMCGroup.id).filter(
            HMCGroupWing.wing_id == complaint.affected_wing_id,
            HMCGroupWing.building_id == complaint.affected_building_id,
            HMCGroupWing.floor_id == complaint.affected_floor_id,
        )
    return {g.id for g in q.all() if _valid_hmc_group(db, g)}


def _assert_moderator(db: Session, reviewer: User, complaint: Complaint) -> set[int] | None:
    if reviewer.role == "admin" and reviewer.is_active:
        return None
    if reviewer.role != "staff" or not reviewer.is_active:
        raise HTTPException(status_code=403, detail="Only a designated HMC moderator or administrator can moderate publication.")
    relevant = _group_ids_for_complaint(db, complaint)
    assigned = {row.hmc_group_id for row in db.query(HMCGroupModerator).filter(HMCGroupModerator.user_id == reviewer.id).all()}
    allowed = relevant & assigned
    if not allowed:
        raise HTTPException(status_code=403, detail="This staff account is not a designated moderator for the affected HMC location.")
    return allowed


def list_hmc_publication_review_queue(db: Session, reviewer: User, *, department_id: int | None = None,
                                      limit: int = 50, offset: int = 0):
    if reviewer.role == "admin" and reviewer.is_active:
        assigned_group_ids = None
    else:
        if reviewer.role != "staff" or not reviewer.is_active:
            raise HTTPException(status_code=403, detail="Only HMC moderators or administrators can review feed publication.")
        assigned_group_ids = {row.hmc_group_id for row in db.query(HMCGroupModerator).filter(HMCGroupModerator.user_id == reviewer.id).all()}
        if not assigned_group_ids:
            raise HTTPException(status_code=403, detail="This staff account is not designated as an HMC moderator.")
    query = db.query(Complaint).options(
        joinedload(Complaint.department), joinedload(Complaint.affected_building),
        joinedload(Complaint.affected_floor), joinedload(Complaint.affected_wing), joinedload(Complaint.creator),
    ).join(Department, Department.id == Complaint.department_id).filter(
        Complaint.is_public.is_(True),
        Complaint.publication_status.in_([PUBLICATION_PENDING_REVIEW, PUBLICATION_PENDING_MAPPING]),
        Department.is_active.is_(True),
    )
    if department_id is not None:
        query = query.filter(Complaint.department_id == department_id)
    clamped_limit, clamped_offset = max(1, min(limit, 100)), max(0, offset)
    records = query.order_by(Complaint.created_at.asc(), Complaint.id.asc()).all()
    selected = []
    for item in records:
        groups = _group_ids_for_complaint(db, item)
        # Mapping-ambiguous entries are visible only to administrators for resolution.
        if assigned_group_ids is None or (groups and groups & assigned_group_ids):
            selected.append(item)
    total = len(selected)
    selected = selected[clamped_offset:clamped_offset + clamped_limit]
    items = [FeedReviewQueueItem(
        id=item.id, title=item.title, description=item.description,
        department_id=item.department_id,
        department_name=item.department.name if item.department else "Unknown", status=item.status,
        affected_building_id=item.affected_building_id,
        affected_building_name=item.affected_building.name if item.affected_building else None,
        affected_floor_id=item.affected_floor_id,
        affected_floor_name=item.affected_floor.name if item.affected_floor else None,
        affected_wing_id=item.affected_wing_id,
        affected_wing_name=item.affected_wing.name if item.affected_wing else None,
        created_at=item.created_at, publication_status=item.publication_status,
        reporter_id=item.created_by_id, reporter_name=item.creator.name if item.creator else None,
        reporter_email=item.creator.email if item.creator else None,
    ) for item in selected]
    return items, total


def _validate_shared_floor_audience(db: Session, complaint: Complaint, group_ids: list[int] | None) -> list[int]:
    """Validate an explicit HMC audience for a wing-less/shared-floor complaint."""
    if complaint.affected_wing_id is not None:
        if group_ids:
            raise HTTPException(status_code=422, detail="audience_group_ids are only accepted for shared-floor complaints.")
        return []
    if not group_ids:
        raise HTTPException(status_code=422, detail="Select the exact HMC audience for a shared-floor complaint before approving it.")
    if len(group_ids) != len(set(group_ids)):
        raise HTTPException(status_code=422, detail="audience_group_ids must not contain duplicates.")
    available = {
        group.id
        for group in db.query(HMCGroup).filter(
            HMCGroup.building_id == complaint.affected_building_id,
            HMCGroup.floor_id == complaint.affected_floor_id,
            HMCGroup.is_active.is_(True),
        ).all()
        if _valid_hmc_group(db, group)
    }
    requested = set(group_ids)
    if not requested or not requested.issubset(available):
        raise HTTPException(status_code=422, detail="Every audience group must be active and mapped to this building/floor.")
    return sorted(requested)


def review_hmc_publication(db: Session, reviewer: User, complaint_id: int, payload: FeedReviewRequest) -> FeedReviewResult:
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if complaint is None or complaint.visibility_scope != SCOPE_HMC_GROUP_PUBLIC or not complaint.is_public:
        raise HTTPException(status_code=404, detail="HMC review item not found.")
    _assert_moderator(db, reviewer, complaint)
    if complaint.publication_status not in (PUBLICATION_PENDING_REVIEW, PUBLICATION_PENDING_MAPPING):
        raise HTTPException(status_code=409, detail="This complaint is no longer awaiting publication review.")
    if payload.decision == "rejected" and not payload.note:
        raise HTTPException(status_code=422, detail="A reason is required when rejecting publication.")
    selected_audience_ids: list[int] = []
    if payload.decision == "approved":
        if complaint.affected_wing_id is None:
            selected_audience_ids = _validate_shared_floor_audience(
                db, complaint, payload.audience_group_ids
            )
        elif not _has_valid_hmc_mapping(db, complaint):
            raise HTTPException(status_code=409, detail="Cannot publish until the location and active HMC mapping are valid.")
    new_status = PUBLICATION_PUBLISHED if payload.decision == "approved" else PUBLICATION_REJECTED
    legacy_status = REVIEW_APPROVED if payload.decision == "approved" else REVIEW_REJECTED
    previous = complaint.publication_status
    now = datetime.now(timezone.utc)
    result = db.execute(update(Complaint).where(
        Complaint.id == complaint.id,
        Complaint.publication_status.in_([PUBLICATION_PENDING_REVIEW, PUBLICATION_PENDING_MAPPING]),
    ).values(
        publication_status=new_status, feed_review_status=legacy_status,
        feed_reviewed_by_id=reviewer.id, feed_reviewed_at=now, feed_review_note=payload.note,
    ).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This complaint is no longer awaiting publication review.")
    if payload.decision == "approved" and complaint.affected_wing_id is None:
        # Replace the audience atomically with the publication decision.
        db.query(ComplaintHMCGroupAudience).filter(
            ComplaintHMCGroupAudience.complaint_id == complaint.id
        ).delete(synchronize_session=False)
        for group_id in selected_audience_ids:
            db.add(ComplaintHMCGroupAudience(
                complaint_id=complaint.id, hmc_group_id=group_id,
                assigned_by_user_id=reviewer.id,
            ))
    db.add(ComplaintPublicationAudit(
        complaint_id=complaint.id, actor_user_id=reviewer.id, action=payload.decision,
        previous_status=previous, new_status=new_status, note=payload.note,
    ))
    db.commit()
    db.refresh(complaint)
    return FeedReviewResult(
        id=complaint.id, feed_review_status=legacy_status, publication_status=new_status,
        feed_reviewed_at=complaint.feed_reviewed_at,
        message="Publication approved." if payload.decision == "approved" else "Publication rejected; complaint remains in the department workflow.",
    )


def _has_valid_hmc_mapping(db: Session, complaint: Complaint) -> bool:
    if complaint.affected_building_id is None or complaint.affected_floor_id is None:
        return False
    building = db.query(Building).filter(Building.id == complaint.affected_building_id, Building.is_active.is_(True)).first()
    floor = db.query(Floor).filter(Floor.id == complaint.affected_floor_id,
        Floor.building_id == complaint.affected_building_id, Floor.is_active.is_(True)).first()
    if building is None or floor is None:
        return False
    if complaint.affected_wing_id is not None:
        wing = db.query(Wing).filter(Wing.id == complaint.affected_wing_id,
            Wing.building_id == complaint.affected_building_id, Wing.is_active.is_(True)).first()
        if wing is None:
            return False
        return _group_for_location(db, building.id, floor.id, wing.id) is not None
    groups = db.query(HMCGroup).filter(HMCGroup.building_id == building.id,
        HMCGroup.floor_id == floor.id, HMCGroup.is_active.is_(True)).all()
    return any(_valid_hmc_group(db, group) for group in groups)


def verify_student_residence(db: Session, admin: User, student_id: int, *, building_id: int,
                             floor_id: int, wing_id: int) -> User:
    if admin.role != "admin" or not admin.is_active:
        raise HTTPException(status_code=403, detail="Only an active administrator can verify residence assignments.")
    student = db.query(User).filter(User.id == student_id, User.role == "student", User.is_active.is_(True)).first()
    building = db.query(Building).filter(Building.id == building_id, Building.is_active.is_(True)).first()
    floor = db.query(Floor).filter(Floor.id == floor_id, Floor.building_id == building_id, Floor.is_active.is_(True)).first()
    wing = db.query(Wing).filter(Wing.id == wing_id, Wing.building_id == building_id, Wing.is_active.is_(True)).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Active student not found.")
    if building is None or floor is None or wing is None:
        raise HTTPException(status_code=422, detail="Building, floor and wing must be active and belong to the same building.")
    # Assignment changes clear any old verification before writing this verified mapping.
    student.residence_building_id = building.id
    student.residence_floor_id = floor.id
    student.wing_id = wing.id
    student.residence_verified_at = datetime.now(timezone.utc)
    student.residence_verified_by_id = admin.id
    db.commit()
    db.refresh(student)
    return student


def assign_hmc_moderator(db: Session, admin: User, group_id: int, user_id: int, *, assigned: bool = True) -> None:
    if admin.role != "admin" or not admin.is_active:
        raise HTTPException(status_code=403, detail="Only an active administrator can designate HMC moderators.")
    group = db.query(HMCGroup).filter(HMCGroup.id == group_id, HMCGroup.is_active.is_(True)).first()
    user = db.query(User).filter(User.id == user_id, User.role == "staff", User.is_active.is_(True)).first()
    if group is None:
        raise HTTPException(status_code=404, detail="HMC group not found.")
    if user is None:
        raise HTTPException(status_code=404, detail="Active staff user not found.")
    existing = db.query(HMCGroupModerator).filter(
        HMCGroupModerator.hmc_group_id == group_id, HMCGroupModerator.user_id == user_id
    ).first()
    if assigned and existing is None:
        db.add(HMCGroupModerator(hmc_group_id=group_id, user_id=user_id, assigned_by_user_id=admin.id))
    elif not assigned and existing is not None:
        db.delete(existing)
    db.commit()


def unpublish_hmc_complaint(db: Session, actor: User, complaint_id: int, note: str) -> Complaint:
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if complaint is None or not complaint.is_public:
        raise HTTPException(status_code=404, detail="Public complaint not found.")
    if complaint.visibility_scope != SCOPE_HMC_GROUP_PUBLIC and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Only administrators may unpublish department-wide complaints.")
    _assert_moderator(db, actor, complaint)
    if complaint.publication_status != PUBLICATION_PUBLISHED:
        raise HTTPException(status_code=409, detail="Only currently published complaints can be unpublished.")
    previous = complaint.publication_status
    now = datetime.now(timezone.utc)
    complaint.publication_status = PUBLICATION_REJECTED
    complaint.feed_review_status = REVIEW_REJECTED
    complaint.feed_reviewed_by_id = actor.id
    complaint.feed_reviewed_at = now
    complaint.feed_review_note = note.strip()
    db.add(ComplaintPublicationAudit(
        complaint_id=complaint.id, actor_user_id=actor.id, action="unpublished",
        previous_status=previous, new_status=PUBLICATION_REJECTED, note=note.strip(),
    ))
    db.commit()
    db.refresh(complaint)
    return complaint
