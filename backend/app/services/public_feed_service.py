"""Public-feed visibility and hostel publication moderation (Model 2, Sprint 4 S4-09).

Rules (API contract sections 7 and 8):

- ``is_public`` is only the student's request; a complaint appears in a feed
  only when ``publication_status == 'published'``.
- Department feeds contain published, non-located, non-Hostel complaints.
- A complaint with a canonical ``floor_id``, legacy location text or the Hostel
  department is hostel-scoped, whichever department it is assigned to. The
  stored ``visibility_scope`` value stays ``hmc_group_public`` (migration 0011
  CHECK constraint).
- A verified resident sees published hostel-scoped complaints located in their
  own hostel, narrowed by ``scope`` to the whole hostel, their wing or their
  own floor. Residence counts only while verified by an active staff/admin and
  while its floor, wing and hostel are active.
- A verified resident's public complaint about their own hostel publishes
  immediately; every other located public complaint waits for review.
- Review and unpublish belong to active admins and active Hostel-department
  staff. HMC groups and audience rows are no longer read for visibility; the
  group helpers below remain only for the demo seed and the HMC import script.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.models.complaint import Complaint
from app.models.complaint_publication_audit import ComplaintPublicationAudit
from app.models.department import Department
from app.models.hmc_group import HMCGroup, HMCGroupFloor
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence
from app.models.user import User
from app.schemas.public_feed import (
    FeedItem, FeedReviewQueueItem, FeedReviewRequest, FeedReviewResult, HostelFeedItem,
)
from app.services.location_service import (
    get_active_floor, get_active_hostel, get_active_hostel_department,
    hostel_department_name_matches, is_hostel_department, is_hostel_staff,
)

SCOPE_PRIVATE = "private"
SCOPE_DEPARTMENT_PUBLIC = "department_public"
# Stored value kept from migration 0011 (CHECK constraint); means "hostel-scoped" since S4-09.
SCOPE_HOSTEL_PUBLIC = "hmc_group_public"
SCOPE_HMC_GROUP_PUBLIC = SCOPE_HOSTEL_PUBLIC
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
PENDING_PUBLICATION = (PUBLICATION_PENDING_REVIEW, PUBLICATION_PENDING_MAPPING)
FEED_SCOPE_HOSTEL = "hostel"
FEED_SCOPE_WING = "wing"
FEED_SCOPE_FLOOR = "floor"


def coded_error(status_code: int, code: str, message: str) -> HTTPException:
    """Sprint 3 structured error: {"detail": {"code": ..., "message": ...}}."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


# --- HMC group data (not used for visibility since S4-09) --------------------

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
    """Data helper for the HMC import script; grants no visibility."""
    if student.role != "student":
        return None
    floor = verified_residence_floor(db, student)
    return hmc_group_for_floor(db, floor.id) if floor else None


# --- Verified residence -------------------------------------------------------

def student_residence_floor(db: Session, student: User) -> HostelFloor | None:
    """A student's verified, fully active residence floor (wing and hostel loaded), else None."""
    if student.role != "student":
        return None
    return verified_residence_floor(db, student)


def require_student_residence_floor(db: Session, student: User) -> HostelFloor:
    floor = student_residence_floor(db, student)
    if floor is None:
        raise coded_error(
            status.HTTP_403_FORBIDDEN, "residence_not_verified",
            "Your hostel residence is not verified, or its floor, wing or hostel is inactive.",
        )
    return floor


def can_moderate_hostel(db: Session, user: User) -> bool:
    """Active admins and active Hostel-department staff review and unpublish hostel complaints."""
    if not user.is_active:
        return False
    return user.role == "admin" or is_hostel_staff(db, user)


# --- Classification on submission -------------------------------------------

@dataclass(frozen=True)
class ComplaintVisibility:
    visibility_scope: str
    feed_review_status: str
    publication_status: str


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
    if floor is None:
        return ComplaintVisibility(SCOPE_HOSTEL_PUBLIC, REVIEW_PENDING, PUBLICATION_PENDING_MAPPING)
    residence_floor = student_residence_floor(db, student)
    if residence_floor is not None and residence_floor.wing.hostel_id == floor.wing.hostel_id:
        # Model 2: a verified resident's report about their own hostel publishes immediately.
        return ComplaintVisibility(SCOPE_HOSTEL_PUBLIC, REVIEW_AUTO_APPROVED, PUBLICATION_PUBLISHED)
    return ComplaintVisibility(SCOPE_HOSTEL_PUBLIC, REVIEW_PENDING, PUBLICATION_PENDING_REVIEW)


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


def hostel_published_conditions() -> list:
    """Published hostel-scoped complaints on a canonical floor. Requires a Department join."""
    return [
        Complaint.is_public.is_(True),
        Complaint.publication_status == PUBLICATION_PUBLISHED,
        Complaint.visibility_scope == SCOPE_HOSTEL_PUBLIC,
        Complaint.floor_id.isnot(None),
        Department.is_active.is_(True),
    ]


def _floor_ids_in_hostel(hostel_id: int):
    return (
        select(HostelFloor.id)
        .join(HostelWing, HostelWing.id == HostelFloor.wing_id)
        .where(HostelWing.hostel_id == hostel_id)
    )


def resident_visible_conditions(residence_floor: HostelFloor, scope: str = FEED_SCOPE_HOSTEL) -> list:
    """What a verified resident may see: published complaints in their hostel, narrowed by scope."""
    if scope == FEED_SCOPE_FLOOR:
        location = Complaint.floor_id == residence_floor.id
    elif scope == FEED_SCOPE_WING:
        location = Complaint.floor_id.in_(select(HostelFloor.id).where(HostelFloor.wing_id == residence_floor.wing_id))
    elif scope == FEED_SCOPE_HOSTEL:
        location = Complaint.floor_id.in_(_floor_ids_in_hostel(residence_floor.wing.hostel_id))
    else:  # Defensive: the route validates scope; never widen on an unknown value.
        raise ValueError(f"Unknown feed scope: {scope!r}")
    return [*hostel_published_conditions(), location]


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


def list_hostel_feed(db: Session, user: User, *, hostel_id: int | None = None, scope: str | None = None,
                     status_filter: str | None = None, limit: int = 20, offset: int = 0):
    """Model 2: residents see their own hostel (narrowed by scope); Hostel staff/admins see every hostel."""
    if get_active_hostel_department(db) is None:
        raise HTTPException(status_code=404, detail="Hostel department not found.")
    if user.role == "student":
        if hostel_id is not None:
            raise coded_error(403, "hostel_selection_forbidden", "Students cannot select a hostel.")
        residence_floor = require_student_residence_floor(db, user)
        query = _feed_query(db).filter(*resident_visible_conditions(residence_floor, scope or FEED_SCOPE_HOSTEL))
    elif user.role == "admin" or is_hostel_staff(db, user):
        if scope is not None:
            raise coded_error(403, "scope_selection_forbidden",
                              "The wing and floor scopes apply to students; use hostel_id instead.")
        query = _feed_query(db).filter(*hostel_published_conditions())
        if hostel_id is not None:
            if get_active_hostel(db, hostel_id) is None:
                raise coded_error(404, "hostel_not_found", "Hostel not found or inactive.")
            query = query.filter(Complaint.floor_id.in_(_floor_ids_in_hostel(hostel_id)))
    else:
        raise HTTPException(status_code=403, detail="Only Hostel-department staff, administrators or verified residents can view the hostel feed.")
    if status_filter:
        query = query.filter(Complaint.status == status_filter)
    return _limited(query, _hostel_feed_item, limit, offset)


def get_feed_item(db: Session, user: User, complaint_id: int) -> HostelFeedItem:
    """Repeat the feed access rules for a single item; never returns the description."""
    base = _feed_query(db).filter(Complaint.id == complaint_id)
    complaint = base.filter(*department_feed_conditions()).first()
    if complaint is None:
        if user.role == "student":
            residence_floor = student_residence_floor(db, user)
            if residence_floor is not None:
                complaint = base.filter(*resident_visible_conditions(residence_floor)).first()
        elif user.role == "admin" or is_hostel_staff(db, user):
            complaint = base.filter(*hostel_published_conditions()).first()
    if complaint is None:
        raise HTTPException(status_code=404, detail="Feed complaint not found.")
    return _hostel_feed_item(complaint)


# --- Moderation --------------------------------------------------------------

def _assert_moderator(db: Session, reviewer: User, complaint: Complaint) -> None:
    """Active admins; or active Hostel-department staff for a complaint with a canonical floor."""
    if reviewer.role == "admin" and reviewer.is_active:
        return
    if not can_moderate_hostel(db, reviewer):
        raise HTTPException(status_code=403, detail="Only Hostel-department staff or an administrator can moderate hostel publication.")
    if complaint.floor_id is None:
        raise HTTPException(status_code=403, detail="Only an administrator can moderate a complaint without a canonical floor.")


def _location_names(complaint: Complaint) -> dict:
    floor = complaint.location_floor
    if floor is None:
        return {"hostel": complaint.hostel, "wing": complaint.wing, "floor": complaint.floor}
    return {"hostel": floor.wing.hostel.name, "wing": floor.wing.name, "floor": floor.name}


def list_hmc_publication_review_queue(db: Session, reviewer: User, *, department_id: int | None = None,
                                      limit: int = 50, offset: int = 0):
    if not can_moderate_hostel(db, reviewer):
        raise HTTPException(status_code=403, detail="Only Hostel-department staff or administrators can review feed publication.")
    query = db.query(Complaint).options(
        joinedload(Complaint.department), joinedload(Complaint.creator),
        joinedload(Complaint.location_floor).joinedload(HostelFloor.wing).joinedload(HostelWing.hostel),
    ).join(Department, Department.id == Complaint.department_id).filter(
        Complaint.is_public.is_(True),
        Complaint.visibility_scope == SCOPE_HOSTEL_PUBLIC,
        Complaint.publication_status.in_(PENDING_PUBLICATION),
        Department.is_active.is_(True),
    )
    if reviewer.role != "admin":
        # Unmapped entries are visible only to administrators for resolution.
        query = query.filter(Complaint.floor_id.isnot(None))
    if department_id is not None:
        query = query.filter(Complaint.department_id == department_id)
    clamped_limit, clamped_offset = max(1, min(limit, 100)), max(0, offset)
    total = query.order_by(None).count()
    rows = query.order_by(Complaint.created_at.asc(), Complaint.id.asc()).offset(clamped_offset).limit(clamped_limit).all()
    items = [FeedReviewQueueItem(
        id=item.id, title=item.title, description=item.description,
        department_id=item.department_id,
        department_name=item.department.name if item.department else "Unknown", status=item.status,
        floor_id=item.floor_id, **_location_names(item),
        created_at=item.created_at, publication_status=item.publication_status,
        reporter_id=item.created_by_id, reporter_name=item.creator.name if item.creator else None,
        reporter_email=item.creator.email if item.creator else None,
    ) for item in rows]
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
    if payload.decision == "approved" and (complaint.floor_id is None or get_active_floor(db, complaint.floor_id) is None):
        raise HTTPException(status_code=409, detail="Cannot publish until the complaint has an active canonical floor.")
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
