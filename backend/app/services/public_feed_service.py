"""Public-feed visibility, HMC group membership and HMC publication moderation.

Rules (API contract sections 7 and 8):

- ``is_public`` is only the student's request; a complaint appears in a feed
  only when ``publication_status == 'published'``.
- Department feeds contain published, non-located, non-Hostel complaints.
- A complaint with a canonical ``floor_id``, legacy location text or the Hostel
  department is HMC-scoped, whichever department it is assigned to.
- HMC groups map one or two canonical wing floors on the same hostel floor
  level. Student membership comes only from a staff-verified residence.
- A published HMC complaint is visible to a group only through an explicit
  ``ComplaintHMCAudience`` row. The responsible group is recorded on
  auto-publish or approval; sharing with another group on the same floor level
  is a separate, audited moderator decision. Nothing is broadcast to every
  group on a floor.
- Publication moderation belongs to admins and explicitly designated HMC-group
  moderators, never to department staff membership alone.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session, joinedload

from app.models.complaint import Complaint
from app.models.complaint_hmc_audience import ComplaintHMCAudience
from app.models.complaint_publication_audit import ComplaintPublicationAudit
from app.models.department import Department
from app.models.hmc_group import HMCGroup, HMCGroupFloor
from app.models.hmc_group_moderator import HMCGroupModerator
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence
from app.models.user import User
from app.schemas.public_feed import (
    AudienceItem, FeedItem, FeedReviewQueueItem, FeedReviewRequest, FeedReviewResult,
    HMCGroupSummary, HostelFeedItem,
)
from app.services.location_service import (
    get_active_floor, get_active_hostel, get_active_hostel_department,
    hostel_department_name_matches, is_hostel_department, is_hostel_staff,
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
AUDIENCE_RESPONSIBLE_GROUP = "responsible_group"
AUDIENCE_SHARED_FLOOR = "shared_floor"
PENDING_PUBLICATION = (PUBLICATION_PENDING_REVIEW, PUBLICATION_PENDING_MAPPING)


def coded_error(status_code: int, code: str, message: str) -> HTTPException:
    """Sprint 3 structured error: {"detail": {"code": ..., "message": ...}}."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


# --- HMC group membership ---------------------------------------------------

def valid_hmc_group(db: Session, group: HMCGroup | None) -> bool:
    """One or two active floors, in distinct wings of the group's active hostel, at one floor level."""
    if group is None or not group.is_active or get_active_hostel(db, group.hostel_id) is None:
        return False
    rows = (
        db.query(HostelFloor, HostelWing)
        .join(HMCGroupFloor, HMCGroupFloor.floor_id == HostelFloor.id)
        .join(HostelWing, HostelWing.id == HostelFloor.wing_id)
        .filter(HMCGroupFloor.hmc_group_id == group.id)
        .all()
    )
    return (
        1 <= len(rows) <= 2
        and len({wing.id for _, wing in rows}) == len(rows)
        and all(
            floor.is_active and wing.is_active
            and wing.hostel_id == group.hostel_id
            and floor.code == group.floor_code
            for floor, wing in rows
        )
    )


def hmc_group_for_floor(db: Session, floor_id: int | None) -> HMCGroup | None:
    """The single valid group responsible for a canonical floor, if any."""
    if floor_id is None:
        return None
    mapping = db.query(HMCGroupFloor).filter(HMCGroupFloor.floor_id == floor_id).first()
    group = mapping.group if mapping else None
    return group if valid_hmc_group(db, group) else None


def verified_residence_floor(db: Session, student: User) -> HostelFloor | None:
    """The student's residence floor, only while verified by an active staff/admin and still active."""
    residence = db.query(StudentResidence).filter(
        StudentResidence.student_id == student.id,
        StudentResidence.status == "verified",
        StudentResidence.verified_by_id.isnot(None),
        StudentResidence.verified_at.isnot(None),
    ).first()
    if residence is None:
        return None
    verifier = db.query(User).filter(
        User.id == residence.verified_by_id,
        User.role.in_(["staff", "admin"]),
        User.is_active.is_(True),
    ).first()
    if verifier is None:
        return None
    return get_active_floor(db, residence.floor_id)


def student_hmc_group(db: Session, student: User) -> HMCGroup | None:
    if student.role != "student":
        return None
    floor = verified_residence_floor(db, student)
    return hmc_group_for_floor(db, floor.id) if floor else None


def require_student_hmc_group(db: Session, student: User) -> HMCGroup:
    group = student_hmc_group(db, student)
    if group is None:
        raise coded_error(
            status.HTTP_403_FORBIDDEN, "residence_not_verified",
            "Your residence is not verified or is not mapped to a valid HMC group.",
        )
    return group


# --- Classification on submission -------------------------------------------

@dataclass(frozen=True)
class ComplaintVisibility:
    visibility_scope: str
    feed_review_status: str
    publication_status: str
    audience_group_id: int | None = None


def classify_complaint_visibility(
    db: Session, student: User, *, is_public: bool, floor: HostelFloor | None,
    has_legacy_location: bool, is_hostel: bool,
) -> ComplaintVisibility:
    """Server-side publication decision; the client never chooses scope or group."""
    if not is_public:
        return ComplaintVisibility(SCOPE_PRIVATE, REVIEW_NOT_REQUIRED, PUBLICATION_PRIVATE)
    if floor is None and not has_legacy_location and not is_hostel:
        return ComplaintVisibility(SCOPE_DEPARTMENT_PUBLIC, REVIEW_NOT_REQUIRED, PUBLICATION_PUBLISHED)
    # Unlocated Hostel complaints and text-only locations are never guessed.
    responsible = hmc_group_for_floor(db, floor.id) if floor is not None else None
    if responsible is None:
        return ComplaintVisibility(SCOPE_HMC_GROUP_PUBLIC, REVIEW_PENDING, PUBLICATION_PENDING_MAPPING)
    reporter_group = student_hmc_group(db, student)
    if reporter_group is not None and reporter_group.id == responsible.id:
        return ComplaintVisibility(
            SCOPE_HMC_GROUP_PUBLIC, REVIEW_AUTO_APPROVED, PUBLICATION_PUBLISHED, responsible.id,
        )
    return ComplaintVisibility(SCOPE_HMC_GROUP_PUBLIC, REVIEW_PENDING, PUBLICATION_PENDING_REVIEW)


def add_responsible_audience(db: Session, complaint_id: int, group_id: int, actor_id: int) -> None:
    """Record the responsible group's authorization; the caller commits."""
    existing = db.query(ComplaintHMCAudience).filter(
        ComplaintHMCAudience.complaint_id == complaint_id,
        ComplaintHMCAudience.hmc_group_id == group_id,
    ).first()
    if existing is None:
        db.add(ComplaintHMCAudience(
            complaint_id=complaint_id, hmc_group_id=group_id,
            source=AUDIENCE_RESPONSIBLE_GROUP, decided_by_id=actor_id,
        ))


# --- Visibility conditions (shared by feeds, details and duplicates) ---------

def _no_legacy_location():
    return [
        func.trim(func.coalesce(Complaint.hostel, "")) == "",
        func.trim(func.coalesce(Complaint.wing, "")) == "",
        func.trim(func.coalesce(Complaint.floor, "")) == "",
    ]


def department_feed_conditions() -> list:
    """Published, department-wide, non-located, non-Hostel. Requires a Department join."""
    return [
        Complaint.is_public.is_(True),
        Complaint.publication_status == PUBLICATION_PUBLISHED,
        Complaint.visibility_scope == SCOPE_DEPARTMENT_PUBLIC,
        Complaint.floor_id.is_(None),
        *_no_legacy_location(),
        Department.is_active.is_(True),
        ~hostel_department_name_matches(),
    ]


def _hmc_published_conditions() -> list:
    """Published HMC complaints on a canonical floor. Requires a Department join."""
    return [
        Complaint.is_public.is_(True),
        Complaint.publication_status == PUBLICATION_PUBLISHED,
        Complaint.visibility_scope == SCOPE_HMC_GROUP_PUBLIC,
        Complaint.floor_id.isnot(None),
        Department.is_active.is_(True),
    ]


def _floors_at_group_level(group: HMCGroup):
    return (
        select(HostelFloor.id)
        .join(HostelWing, HostelWing.id == HostelFloor.wing_id)
        .where(HostelWing.hostel_id == group.hostel_id, HostelFloor.code == group.floor_code)
    )


def hmc_group_visible_conditions(group: HMCGroup) -> list:
    """Published for this group by an explicit audience row, on the group's own floor level."""
    return [
        *_hmc_published_conditions(),
        exists().where(
            ComplaintHMCAudience.complaint_id == Complaint.id,
            ComplaintHMCAudience.hmc_group_id == group.id,
        ),
        Complaint.floor_id.in_(_floors_at_group_level(group)),
    ]


def _authorized_hmc_conditions() -> list:
    """Published HMC complaints authorized for at least one group (internal staff/admin view)."""
    return [
        *_hmc_published_conditions(),
        exists().where(ComplaintHMCAudience.complaint_id == Complaint.id),
    ]


# --- Feeds -----------------------------------------------------------------

def _feed_item(complaint: Complaint) -> FeedItem:
    return FeedItem(
        id=complaint.id, title=complaint.title,
        department_id=complaint.department_id,
        department_name=complaint.department.name if complaint.department else "Unknown",
        status=complaint.status, created_at=complaint.created_at,
        updated_at=complaint.updated_at, reopen_count=complaint.reopen_count,
    )


def _hostel_feed_item(complaint: Complaint) -> HostelFeedItem:
    floor = complaint.location_floor
    return HostelFeedItem(
        **_feed_item(complaint).model_dump(),
        hostel=floor.wing.hostel.name if floor else None,
        wing=floor.wing.name if floor else None,
        floor=floor.name if floor else None,
    )


def _feed_query(db: Session):
    return db.query(Complaint).join(Department, Department.id == Complaint.department_id).options(
        joinedload(Complaint.department),
        joinedload(Complaint.location_floor).joinedload(HostelFloor.wing).joinedload(HostelWing.hostel),
    )


def _limited(query, build, limit: int, offset: int):
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    total = query.order_by(None).count()
    items = query.order_by(Complaint.created_at.desc(), Complaint.id.desc()).offset(offset).limit(limit).all()
    return [build(item) for item in items], total


def list_department_feed(db: Session, *, department_id: int, status_filter: str | None = None,
                         limit: int = 20, offset: int = 0):
    department = db.query(Department).filter(Department.id == department_id, Department.is_active.is_(True)).first()
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found.")
    if is_hostel_department(department):
        raise coded_error(400, "hostel_feed_required", "Use the restricted hostel feed for Hostel complaints.")
    query = _feed_query(db).filter(Complaint.department_id == department_id, *department_feed_conditions())
    if status_filter:
        query = query.filter(Complaint.status == status_filter)
    return _limited(query, _feed_item, limit, offset)


def list_hostel_feed(db: Session, user: User, *, hostel_id: int | None = None,
                     status_filter: str | None = None, limit: int = 20, offset: int = 0):
    """Students see only their verified group's authorized items; Hostel staff/admins see all authorized items."""
    if get_active_hostel_department(db) is None:
        raise HTTPException(status_code=404, detail="Hostel department not found.")
    if user.role == "student":
        if hostel_id is not None:
            raise coded_error(403, "hostel_selection_forbidden", "Students cannot select a hostel.")
        group = require_student_hmc_group(db, user)
        query = _feed_query(db).filter(*hmc_group_visible_conditions(group))
    elif user.role == "admin" or is_hostel_staff(db, user):
        query = _feed_query(db).filter(*_authorized_hmc_conditions())
        if hostel_id is not None:
            if get_active_hostel(db, hostel_id) is None:
                raise coded_error(404, "hostel_not_found", "Hostel not found or inactive.")
            hostel_floors = (
                select(HostelFloor.id)
                .join(HostelWing, HostelWing.id == HostelFloor.wing_id)
                .where(HostelWing.hostel_id == hostel_id)
            )
            query = query.filter(Complaint.floor_id.in_(hostel_floors))
    else:
        raise HTTPException(status_code=403, detail="Only Hostel-department staff, administrators or verified HMC members can view the hostel feed.")
    if status_filter:
        query = query.filter(Complaint.status == status_filter)
    return _limited(query, _hostel_feed_item, limit, offset)


def get_feed_item(db: Session, user: User, complaint_id: int) -> HostelFeedItem:
    """Repeat the feed access rules for a single item; never returns the description."""
    base = _feed_query(db).filter(Complaint.id == complaint_id)
    complaint = base.filter(*department_feed_conditions()).first()
    if complaint is None:
        if user.role == "student":
            group = student_hmc_group(db, user)
            if group is not None:
                complaint = base.filter(*hmc_group_visible_conditions(group)).first()
        elif user.role == "admin" or is_hostel_staff(db, user):
            complaint = base.filter(*_authorized_hmc_conditions()).first()
    if complaint is None:
        raise HTTPException(status_code=404, detail="Feed complaint not found.")
    return _hostel_feed_item(complaint)


# --- Moderation --------------------------------------------------------------

def _moderator_group_ids(db: Session, user: User) -> set[int]:
    return {row.hmc_group_id for row in db.query(HMCGroupModerator).filter(HMCGroupModerator.user_id == user.id).all()}


def _assert_moderator(db: Session, reviewer: User, complaint: Complaint, *extra_group_ids: int) -> None:
    """Admins, or staff designated for the responsible group (and any extra groups involved)."""
    if reviewer.role == "admin" and reviewer.is_active:
        return
    if reviewer.role != "staff" or not reviewer.is_active:
        raise HTTPException(status_code=403, detail="Only a designated HMC moderator or administrator can moderate publication.")
    responsible = hmc_group_for_floor(db, complaint.floor_id)
    required = {responsible.id, *extra_group_ids} if responsible else None
    if not required or not required <= _moderator_group_ids(db, reviewer):
        raise HTTPException(status_code=403, detail="This staff account is not a designated moderator for the affected HMC group.")


def _location_names(complaint: Complaint) -> dict:
    floor = complaint.location_floor
    if floor is None:
        return {"hostel": complaint.hostel, "wing": complaint.wing, "floor": complaint.floor}
    return {"hostel": floor.wing.hostel.name, "wing": floor.wing.name, "floor": floor.name}


def list_hmc_publication_review_queue(db: Session, reviewer: User, *, department_id: int | None = None,
                                      limit: int = 50, offset: int = 0):
    if reviewer.role == "admin" and reviewer.is_active:
        assigned_group_ids = None
    else:
        if reviewer.role != "staff" or not reviewer.is_active:
            raise HTTPException(status_code=403, detail="Only HMC moderators or administrators can review feed publication.")
        assigned_group_ids = _moderator_group_ids(db, reviewer)
        if not assigned_group_ids:
            raise HTTPException(status_code=403, detail="This staff account is not designated as an HMC moderator.")
    query = db.query(Complaint).options(
        joinedload(Complaint.department), joinedload(Complaint.creator),
        joinedload(Complaint.location_floor).joinedload(HostelFloor.wing).joinedload(HostelWing.hostel),
    ).join(Department, Department.id == Complaint.department_id).filter(
        Complaint.is_public.is_(True),
        Complaint.publication_status.in_(PENDING_PUBLICATION),
        Department.is_active.is_(True),
    )
    if department_id is not None:
        query = query.filter(Complaint.department_id == department_id)
    clamped_limit, clamped_offset = max(1, min(limit, 100)), max(0, offset)
    selected = []
    for item in query.order_by(Complaint.created_at.asc(), Complaint.id.asc()).all():
        group = hmc_group_for_floor(db, item.floor_id)
        # Unmapped entries are visible only to administrators for resolution.
        if assigned_group_ids is None or (group is not None and group.id in assigned_group_ids):
            selected.append((item, group))
    total = len(selected)
    items = [FeedReviewQueueItem(
        id=item.id, title=item.title, description=item.description,
        department_id=item.department_id,
        department_name=item.department.name if item.department else "Unknown", status=item.status,
        floor_id=item.floor_id, **_location_names(item),
        responsible_hmc_group_id=group.id if group else None,
        created_at=item.created_at, publication_status=item.publication_status,
        reporter_id=item.created_by_id, reporter_name=item.creator.name if item.creator else None,
        reporter_email=item.creator.email if item.creator else None,
    ) for item, group in selected[clamped_offset:clamped_offset + clamped_limit]]
    return items, total


def review_hmc_publication(db: Session, reviewer: User, complaint_id: int, payload: FeedReviewRequest) -> FeedReviewResult:
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if complaint is None or complaint.visibility_scope != SCOPE_HMC_GROUP_PUBLIC or not complaint.is_public:
        raise HTTPException(status_code=404, detail="HMC review item not found.")
    _assert_moderator(db, reviewer, complaint)
    if complaint.publication_status not in PENDING_PUBLICATION:
        raise HTTPException(status_code=409, detail="This complaint is no longer awaiting publication review.")
    if payload.decision == "rejected" and not payload.note:
        raise HTTPException(status_code=422, detail="A reason is required when rejecting publication.")
    responsible = hmc_group_for_floor(db, complaint.floor_id)
    if payload.decision == "approved" and responsible is None:
        raise HTTPException(status_code=409, detail="Cannot publish until the canonical floor and an active HMC group mapping are valid.")
    new_status = PUBLICATION_PUBLISHED if payload.decision == "approved" else PUBLICATION_REJECTED
    legacy_status = REVIEW_APPROVED if payload.decision == "approved" else REVIEW_REJECTED
    previous = complaint.publication_status
    now = datetime.now(timezone.utc)
    result = db.execute(update(Complaint).where(
        Complaint.id == complaint.id,
        Complaint.publication_status.in_(PENDING_PUBLICATION),
    ).values(
        publication_status=new_status, feed_review_status=legacy_status,
        feed_reviewed_by_id=reviewer.id, feed_reviewed_at=now, feed_review_note=payload.note,
    ).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This complaint is no longer awaiting publication review.")
    if payload.decision == "approved":
        # Approval authorizes the responsible group only; sharing needs a separate decision.
        add_responsible_audience(db, complaint.id, responsible.id, reviewer.id)
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


def unpublish_hmc_complaint(db: Session, actor: User, complaint_id: int, note: str) -> Complaint:
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if complaint is None or not complaint.is_public:
        raise HTTPException(status_code=404, detail="Public complaint not found.")
    if complaint.visibility_scope != SCOPE_HMC_GROUP_PUBLIC and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Only administrators may unpublish department-wide complaints.")
    if complaint.visibility_scope == SCOPE_HMC_GROUP_PUBLIC:
        _assert_moderator(db, actor, complaint)
    if complaint.publication_status != PUBLICATION_PUBLISHED:
        raise HTTPException(status_code=409, detail="Only currently published complaints can be unpublished.")
    previous = complaint.publication_status
    complaint.publication_status = PUBLICATION_REJECTED
    complaint.feed_review_status = REVIEW_REJECTED
    complaint.feed_reviewed_by_id = actor.id
    complaint.feed_reviewed_at = datetime.now(timezone.utc)
    complaint.feed_review_note = note.strip()
    db.add(ComplaintPublicationAudit(
        complaint_id=complaint.id, actor_user_id=actor.id, action="unpublished",
        previous_status=previous, new_status=PUBLICATION_REJECTED, note=note.strip(),
    ))
    db.commit()
    db.refresh(complaint)
    return complaint


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


# --- Shared-floor audiences ---------------------------------------------------

def _published_hmc_complaint(db: Session, complaint_id: int) -> Complaint:
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if complaint is None or complaint.visibility_scope != SCOPE_HMC_GROUP_PUBLIC or not complaint.is_public:
        raise HTTPException(status_code=404, detail="HMC complaint not found.")
    return complaint


def list_complaint_audiences(db: Session, actor: User, complaint_id: int) -> list[AudienceItem]:
    complaint = _published_hmc_complaint(db, complaint_id)
    _assert_moderator(db, actor, complaint)
    rows = db.query(ComplaintHMCAudience).options(joinedload(ComplaintHMCAudience.group)).filter(
        ComplaintHMCAudience.complaint_id == complaint.id
    ).order_by(ComplaintHMCAudience.id).all()
    return [AudienceItem(
        hmc_group_id=row.hmc_group_id, hmc_group_name=row.group.name, source=row.source,
        decided_by_id=row.decided_by_id, created_at=row.created_at,
    ) for row in rows]


def grant_shared_floor_audience(db: Session, actor: User, complaint_id: int, group_id: int, note: str) -> list[AudienceItem]:
    """Share a published complaint with another valid group on the same hostel floor level."""
    complaint = _published_hmc_complaint(db, complaint_id)
    _assert_moderator(db, actor, complaint, group_id)
    if complaint.publication_status != PUBLICATION_PUBLISHED:
        raise HTTPException(status_code=409, detail="Only published complaints can be shared with another HMC group.")
    responsible = hmc_group_for_floor(db, complaint.floor_id)
    if responsible is None:
        raise HTTPException(status_code=409, detail="The complaint's floor has no valid responsible HMC group.")
    target = db.query(HMCGroup).filter(HMCGroup.id == group_id).first()
    if target is None or not valid_hmc_group(db, target):
        raise HTTPException(status_code=404, detail="HMC group not found or not valid.")
    floor = get_active_floor(db, complaint.floor_id)
    if (
        target.id == responsible.id
        or floor is None
        or target.hostel_id != floor.wing.hostel_id
        or target.floor_code != floor.code
    ):
        raise HTTPException(status_code=422, detail="A shared-floor audience must be a different HMC group on the same hostel floor level.")
    if db.query(ComplaintHMCAudience).filter(
        ComplaintHMCAudience.complaint_id == complaint.id, ComplaintHMCAudience.hmc_group_id == target.id
    ).first() is not None:
        raise HTTPException(status_code=409, detail="This HMC group is already an audience for the complaint.")
    db.add(ComplaintHMCAudience(
        complaint_id=complaint.id, hmc_group_id=target.id, source=AUDIENCE_SHARED_FLOOR,
        decided_by_id=actor.id, note=note,
    ))
    db.add(ComplaintPublicationAudit(
        complaint_id=complaint.id, actor_user_id=actor.id, action="audience_added",
        previous_status=complaint.publication_status, new_status=complaint.publication_status,
        note=f"HMC group {target.id}: {note}",
    ))
    db.commit()
    return list_complaint_audiences(db, actor, complaint.id)


def revoke_shared_floor_audience(db: Session, actor: User, complaint_id: int, group_id: int, note: str) -> list[AudienceItem]:
    complaint = _published_hmc_complaint(db, complaint_id)
    _assert_moderator(db, actor, complaint, group_id)
    row = db.query(ComplaintHMCAudience).filter(
        ComplaintHMCAudience.complaint_id == complaint.id, ComplaintHMCAudience.hmc_group_id == group_id
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="This HMC group is not an audience for the complaint.")
    if row.source != AUDIENCE_SHARED_FLOOR:
        raise HTTPException(status_code=409, detail="The responsible group cannot be removed; unpublish the complaint instead.")
    db.delete(row)
    db.add(ComplaintPublicationAudit(
        complaint_id=complaint.id, actor_user_id=actor.id, action="audience_removed",
        previous_status=complaint.publication_status, new_status=complaint.publication_status,
        note=f"HMC group {group_id}: {note}",
    ))
    db.commit()
    return list_complaint_audiences(db, actor, complaint.id)


def list_hmc_groups(db: Session, actor: User) -> list[HMCGroupSummary]:
    if not (actor.role == "admin" or (actor.role == "staff" and _moderator_group_ids(db, actor))):
        raise HTTPException(status_code=403, detail="Only HMC moderators or administrators can list HMC groups.")
    groups = db.query(HMCGroup).options(joinedload(HMCGroup.hostel), joinedload(HMCGroup.floor_assignments)).order_by(
        HMCGroup.hostel_id, HMCGroup.floor_code, HMCGroup.name
    ).all()
    return [HMCGroupSummary(
        id=group.id, name=group.name, hostel_id=group.hostel_id, hostel_name=group.hostel.name,
        floor_code=group.floor_code, floor_ids=sorted(row.floor_id for row in group.floor_assignments),
        is_active=group.is_active, is_valid=valid_hmc_group(db, group),
    ) for group in groups]
