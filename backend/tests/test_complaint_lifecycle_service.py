"""Comprehensive acceptance and unit tests for the Complaint Lifecycle Service.

Covers:
1. Lifecycle State Machine transitions (submitted -> in_progress -> resolved; reopened -> in_progress)
2. Invalid state transitions (409 Conflict)
3. Department isolation enforcement (404 Not Found)
4. Initial submission history record creation on new complaints
5. Reopen rules (author ownership 404, resolved state 409, 7-day limit 400, max 2 reopens 400)
6. Public feed query with filters (department, status, hostel, wing, floor, pagination, privacy)
7. Rolling-average resolution-time metrics calculation
"""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.user import User
from app.schemas.complaint import ComplaintCreate
from app.schemas.staff import StaffComplaintStatusUpdate
from app.services.complaint_lifecycle_service import (
    calculate_rolling_resolution_metrics,
    get_public_complaints_feed,
    reopen_student_complaint,
    update_department_complaint_status,
)
from app.services.complaint_service import create_student_complaint


def _create_staff(db: Session, department_id: int | None, name: str = "IT Staff", email: str = "it.staff@campus.edu") -> User:
    staff = User(
        name=name,
        email=email,
        password_hash=None,
        role="staff",
        is_active=True,
        department_id=department_id,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


def _create_complaint(
    db: Session,
    *,
    student_id: int,
    department_id: int,
    title: str = "Network issue",
    status: str = "submitted",
    is_public: bool = False,
    hostel: str | None = None,
    wing: str | None = None,
    floor: str | None = None,
    reopen_count: int = 0,
    created_at: datetime | None = None,
    resolved_at: datetime | None = None,
) -> Complaint:
    now = created_at or datetime.now(timezone.utc)
    complaint = Complaint(
        title=title,
        description="Detailed description for testing complaint lifecycle.",
        department_id=department_id,
        created_by_id=student_id,
        status=status,
        is_public=is_public,
        visibility_scope=("hmc_group_public" if is_public and (hostel or wing or floor) else "department_public" if is_public else "private"),
        feed_review_status=("pending" if is_public and (hostel or wing or floor) else "not_required"),
        publication_status=("pending_mapping" if is_public and (hostel or wing or floor) else "published" if is_public else "private"),
        hostel=hostel,
        wing=wing,
        floor=floor,
        reopen_count=reopen_count,
        created_at=now,
        updated_at=now,
        resolved_at=resolved_at,
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint


# ============================================================================
# 1. Initial Submission Status History Event
# ============================================================================

def test_create_student_complaint_records_initial_history_event(
    db: Session, student_user: User, seeded_departments
):
    target_dept = seeded_departments["it"]
    payload = ComplaintCreate(
        title="Hostel water leakage",
        description="Water leaking in the 2nd floor bathroom block A.",
        department_id=target_dept.id,
    )

    created_resp = create_student_complaint(db, payload, student_user)
    assert created_resp.status == "submitted"

    # Verify atomic creation of ComplaintStatusHistory row
    history_entries = (
        db.query(ComplaintStatusHistory)
        .filter(ComplaintStatusHistory.complaint_id == created_resp.id)
        .all()
    )
    assert len(history_entries) == 1
    initial_event = history_entries[0]
    assert initial_event.from_status is None
    assert initial_event.to_status == "submitted"
    assert initial_event.actor_id == student_user.id
    assert initial_event.created_at is not None


# ============================================================================
# 2. Staff Lifecycle State Machine & History Updates
# ============================================================================

def test_staff_transition_submitted_to_in_progress(
    db: Session, student_user: User, seeded_departments
):
    dept_id = seeded_departments["it"].id
    staff = _create_staff(db, dept_id, name="IT Worker 1", email="worker1@campus.edu")
    complaint = _create_complaint(db, student_id=student_user.id, department_id=dept_id)

    payload = StaffComplaintStatusUpdate(
        status="in_progress",
        remark="Assigned technician to inspect cabling.",
    )

    updated = update_department_complaint_status(db, staff, complaint.id, payload)
    assert updated.status == "in_progress"

    db.refresh(complaint)
    assert complaint.status == "in_progress"
    assert complaint.resolved_at is None

    # Check history record
    history = db.query(ComplaintStatusHistory).filter_by(complaint_id=complaint.id).all()
    assert len(history) == 1
    assert history[0].from_status == "submitted"
    assert history[0].to_status == "in_progress"
    assert history[0].actor_id == staff.id
    assert history[0].remark == "Assigned technician to inspect cabling."


def test_staff_transition_in_progress_to_resolved(
    db: Session, student_user: User, seeded_departments
):
    dept_id = seeded_departments["it"].id
    staff = _create_staff(db, dept_id, name="IT Worker 2", email="worker2@campus.edu")
    complaint = _create_complaint(
        db, student_id=student_user.id, department_id=dept_id, status="in_progress"
    )

    payload = StaffComplaintStatusUpdate(
        status="resolved",
        remark="Replaced damaged port switch. Port is now functional.",
    )

    updated = update_department_complaint_status(db, staff, complaint.id, payload)
    assert updated.status == "resolved"
    assert updated.resolved_at is not None

    db.refresh(complaint)
    assert complaint.status == "resolved"
    assert complaint.resolved_at is not None

    history = db.query(ComplaintStatusHistory).filter_by(complaint_id=complaint.id).all()
    assert len(history) == 1
    assert history[0].from_status == "in_progress"
    assert history[0].to_status == "resolved"
    assert history[0].actor_id == staff.id
    assert history[0].remark == "Replaced damaged port switch. Port is now functional."


def test_staff_transition_reopened_to_in_progress(
    db: Session, student_user: User, seeded_departments
):
    dept_id = seeded_departments["it"].id
    staff = _create_staff(db, dept_id, name="IT Worker 3", email="worker3@campus.edu")
    complaint = _create_complaint(
        db, student_id=student_user.id, department_id=dept_id, status="reopened", reopen_count=1
    )

    payload = StaffComplaintStatusUpdate(
        status="in_progress",
        remark="Reviewing recurring issue.",
    )

    updated = update_department_complaint_status(db, staff, complaint.id, payload)
    assert updated.status == "in_progress"

    db.refresh(complaint)
    assert complaint.status == "in_progress"


def test_staff_transition_disallowed_submitted_to_resolved_raises_409(
    db: Session, student_user: User, seeded_departments
):
    dept_id = seeded_departments["it"].id
    staff = _create_staff(db, dept_id, name="IT Worker 4", email="worker4@campus.edu")
    complaint = _create_complaint(db, student_id=student_user.id, department_id=dept_id, status="submitted")

    payload = StaffComplaintStatusUpdate(
        status="resolved",
        remark="Trying to skip in_progress step.",
    )

    with pytest.raises(HTTPException) as exc_info:
        update_department_complaint_status(db, staff, complaint.id, payload)
    assert exc_info.value.status_code == 409
    assert "Invalid status transition" in exc_info.value.detail


def test_staff_transition_cross_department_raises_404(
    db: Session, student_user: User, seeded_departments
):
    dept_it = seeded_departments["it"].id
    dept_hostel = seeded_departments["hostel"].id
    staff_it = _create_staff(db, dept_it, name="IT Staff Only", email="it_only@campus.edu")
    hostel_complaint = _create_complaint(db, student_id=student_user.id, department_id=dept_hostel)

    payload = StaffComplaintStatusUpdate(
        status="in_progress",
        remark="Cross-department attempt.",
    )

    with pytest.raises(HTTPException) as exc_info:
        update_department_complaint_status(db, staff_it, hostel_complaint.id, payload)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Complaint not found."


def test_staff_without_department_raises_404(
    db: Session, student_user: User, seeded_departments
):
    dept_it = seeded_departments["it"].id
    staff_unassigned = _create_staff(db, None, name="Floating Staff", email="floating@campus.edu")
    complaint = _create_complaint(db, student_id=student_user.id, department_id=dept_it)

    payload = StaffComplaintStatusUpdate(
        status="in_progress",
        remark="Unassigned staff attempt.",
    )

    with pytest.raises(HTTPException) as exc_info:
        update_department_complaint_status(db, staff_unassigned, complaint.id, payload)
    assert exc_info.value.status_code == 404


# ============================================================================
# 3. Student Reopen Rules
# ============================================================================

def test_student_reopen_resolved_complaint_success(
    db: Session, student_user: User, seeded_departments
):
    dept_id = seeded_departments["it"].id
    now = datetime.now(timezone.utc)
    complaint = _create_complaint(
        db,
        student_id=student_user.id,
        department_id=dept_id,
        status="resolved",
        resolved_at=now - timedelta(days=2),
        reopen_count=0,
    )

    reopened = reopen_student_complaint(
        db, student_user, complaint.id, remark="Issue recurred this morning."
    )

    assert reopened.status == "reopened"
    assert reopened.reopen_count == 1
    assert reopened.resolved_at is None

    # Check status history
    history = db.query(ComplaintStatusHistory).filter_by(complaint_id=complaint.id).all()
    assert len(history) == 1
    assert history[0].from_status == "resolved"
    assert history[0].to_status == "reopened"
    assert history[0].actor_id == student_user.id
    assert history[0].remark == "Issue recurred this morning."


def test_student_reopen_non_owner_raises_404(
    db: Session, student_user: User, student_b_user: User, seeded_departments
):
    dept_id = seeded_departments["it"].id
    now = datetime.now(timezone.utc)
    complaint = _create_complaint(
        db,
        student_id=student_user.id,
        department_id=dept_id,
        status="resolved",
        resolved_at=now - timedelta(days=1),
    )

    # Student B tries to reopen Student A's complaint
    with pytest.raises(HTTPException) as exc_info:
        reopen_student_complaint(db, student_b_user, complaint.id)
    assert exc_info.value.status_code == 404
    assert "Complaint not found" in exc_info.value.detail


def test_student_reopen_unresolved_complaint_raises_409(
    db: Session, student_user: User, seeded_departments
):
    dept_id = seeded_departments["it"].id
    complaint = _create_complaint(
        db, student_id=student_user.id, department_id=dept_id, status="in_progress"
    )

    with pytest.raises(HTTPException) as exc_info:
        reopen_student_complaint(db, student_user, complaint.id)
    assert exc_info.value.status_code == 409
    assert "Only resolved complaints can be reopened" in exc_info.value.detail


def test_student_reopen_exceeding_max_count_raises_400(
    db: Session, student_user: User, seeded_departments
):
    dept_id = seeded_departments["it"].id
    now = datetime.now(timezone.utc)
    complaint = _create_complaint(
        db,
        student_id=student_user.id,
        department_id=dept_id,
        status="resolved",
        resolved_at=now - timedelta(days=1),
        reopen_count=2,  # Already reopened 2 times
    )

    with pytest.raises(HTTPException) as exc_info:
        reopen_student_complaint(db, student_user, complaint.id)
    assert exc_info.value.status_code == 400
    assert "maximum allowed reopens" in exc_info.value.detail


def test_student_reopen_after_7_day_window_raises_400(
    db: Session, student_user: User, seeded_departments
):
    dept_id = seeded_departments["it"].id
    now = datetime.now(timezone.utc)
    complaint = _create_complaint(
        db,
        student_id=student_user.id,
        department_id=dept_id,
        status="resolved",
        resolved_at=now - timedelta(days=8),  # 8 days ago > 7 day limit
        reopen_count=0,
    )

    with pytest.raises(HTTPException) as exc_info:
        reopen_student_complaint(db, student_user, complaint.id)
    assert exc_info.value.status_code == 400
    assert "Reopen window expired" in exc_info.value.detail


# ============================================================================
# 4. Public Complaints Feed Query with Filters
# ============================================================================

def test_public_feed_privacy_constraint(
    db: Session, student_user: User, seeded_departments
):
    dept_id = seeded_departments["it"].id
    # Create one public and one private complaint
    public_c = _create_complaint(
        db, student_id=student_user.id, department_id=dept_id, title="Public issue", is_public=True
    )
    private_c = _create_complaint(
        db, student_id=student_user.id, department_id=dept_id, title="Private issue", is_public=False
    )

    items, total = get_public_complaints_feed(db)
    item_ids = [item.id for item in items]

    assert public_c.id in item_ids
    assert private_c.id not in item_ids


def test_public_feed_filtering_by_department(
    db: Session, student_user: User, seeded_departments
):
    dept_it = seeded_departments["it"].id
    dept_hostel = seeded_departments["hostel"].id

    c_it = _create_complaint(
        db, student_id=student_user.id, department_id=dept_it, title="IT issue", is_public=True
    )
    c_hostel = _create_complaint(
        db, student_id=student_user.id, department_id=dept_hostel, title="Hostel issue", is_public=True
    )

    items, total = get_public_complaints_feed(db, department_id=dept_it)
    item_ids = [item.id for item in items]

    assert c_it.id in item_ids
    assert c_hostel.id not in item_ids


def test_location_specific_public_complaints_are_not_in_department_feed(
    db: Session, student_user: User, seeded_departments
):
    """Location-specific public complaints never enter the broad department feed."""
    dept_id = seeded_departments["it"].id
    c1 = _create_complaint(
        db, student_id=student_user.id, department_id=dept_id, title="Wing B water issue",
        is_public=True, wing="B", floor="3",
    )
    c2 = _create_complaint(
        db, student_id=student_user.id, department_id=dept_id, title="Wing A electrical issue",
        is_public=True, wing="A", floor="2",
    )
    assert c1.visibility_scope == "hmc_group_public" and c1.feed_review_status == "pending"
    assert c2.visibility_scope == "hmc_group_public" and c2.feed_review_status == "pending"
    items, total = get_public_complaints_feed(db, department_id=dept_id)
    assert c1.id not in {item.id for item in items}
    assert c2.id not in {item.id for item in items}
    assert total == len(items)


def test_public_feed_pagination(
    db: Session, student_user: User, seeded_departments
):
    dept_id = seeded_departments["it"].id
    base_time = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    for i in range(5):
        _create_complaint(
            db,
            student_id=student_user.id,
            department_id=dept_id,
            title=f"Public Issue {i}",
            is_public=True,
            created_at=base_time + timedelta(minutes=i),
        )

    # Fetch page of size 2, offset 0
    items_p1, total = get_public_complaints_feed(db, limit=2, offset=0)
    assert total >= 5
    assert len(items_p1) == 2
    assert items_p1[0].title == "Public Issue 4"
    assert items_p1[1].title == "Public Issue 3"

    # Fetch page of size 2, offset 2
    items_p2, _ = get_public_complaints_feed(db, limit=2, offset=2)
    assert len(items_p2) == 2
    assert items_p2[0].title == "Public Issue 2"
    assert items_p2[1].title == "Public Issue 1"


# ============================================================================
# 5. Rolling Average Resolution Time Calculation
# ============================================================================

def test_calculate_rolling_resolution_metrics_accurate(
    db: Session, student_user: User, seeded_departments
):
    dept_it = seeded_departments["it"].id
    now = datetime.now(timezone.utc)

    # Complaint 1 resolved in 10 hours
    _create_complaint(
        db,
        student_id=student_user.id,
        department_id=dept_it,
        status="resolved",
        created_at=now - timedelta(days=5, hours=10),
        resolved_at=now - timedelta(days=5),
    )

    # Complaint 2 resolved in 20 hours
    _create_complaint(
        db,
        student_id=student_user.id,
        department_id=dept_it,
        status="resolved",
        created_at=now - timedelta(days=2, hours=20),
        resolved_at=now - timedelta(days=2),
    )

    # Complaint 3 resolved outside 30-day window (35 days ago)
    _create_complaint(
        db,
        student_id=student_user.id,
        department_id=dept_it,
        status="resolved",
        created_at=now - timedelta(days=40),
        resolved_at=now - timedelta(days=35),
    )

    # Complaint 4 not resolved
    _create_complaint(
        db,
        student_id=student_user.id,
        department_id=dept_it,
        status="in_progress",
    )

    metrics = calculate_rolling_resolution_metrics(db, window_days=30, department_id=dept_it)

    assert metrics["resolved_count"] == 2
    # (10 + 20) / 2 = 15.0 hours
    assert metrics["average_resolution_hours"] == 15.0
    # 15 / 24 = 0.62 days
    assert metrics["average_resolution_days"] == 0.62
    assert metrics["min_resolution_hours"] == 10.0
    assert metrics["max_resolution_hours"] == 20.0
    assert metrics["median_resolution_hours"] == 15.0


def test_calculate_rolling_resolution_metrics_empty_dataset(
    db: Session, seeded_departments
):
    # Non-existent department has 0 resolved complaints
    metrics = calculate_rolling_resolution_metrics(db, window_days=30, department_id=99999)
    assert metrics["resolved_count"] == 0
    assert metrics["average_resolution_hours"] is None
    assert metrics["average_resolution_days"] is None
    assert metrics["median_resolution_hours"] is None


def test_calculate_rolling_resolution_metrics_invalid_window_raises_400(db: Session):
    with pytest.raises(HTTPException) as exc_info:
        calculate_rolling_resolution_metrics(db, window_days=0)
    assert exc_info.value.status_code == 400
    assert "positive integer" in exc_info.value.detail

def test_student_reopen_resolved_complaint_missing_resolved_at_is_rejected(
    db: Session, student_user: User, seeded_departments
):
    """A resolved complaint without resolved_at must not bypass the reopen window."""
    dept_id = seeded_departments["it"].id
    complaint = _create_complaint(
        db,
        student_id=student_user.id,
        department_id=dept_id,
        status="resolved",
        resolved_at=None,
        reopen_count=0,
    )

    with pytest.raises(HTTPException) as exc_info:
        reopen_student_complaint(
            db, student_user, complaint.id, remark="Test missing resolution timestamp."
        )

    assert exc_info.value.status_code == 400
    assert "resolution timestamp" in exc_info.value.detail.lower()

    db.refresh(complaint)
    assert complaint.status == "resolved"
    assert complaint.reopen_count == 0
    assert complaint.resolved_at is None
    assert (
        db.query(ComplaintStatusHistory)
        .filter_by(complaint_id=complaint.id)
        .count()
        == 0
    )


def test_staff_rejects_stale_status_update(
    db: Session, student_user, seeded_departments, monkeypatch
):
    """A concurrent state change must invalidate an old staff decision."""
    department_id = seeded_departments["it"].id
    staff = _create_staff(
        db, department_id,
        name="Race Test Staff",
        email="race.staff@campus.edu",
    )
    complaint = _create_complaint(
        db,
        student_id=student_user.id,
        department_id=department_id,
        status="submitted",
    )

    race_db = Session(
        bind=db.connection(),
        join_transaction_mode="create_savepoint",
    )
    original_execute = race_db.execute
    injected = False

    def simulate_competing_write(statement, *args, **kwargs):
        nonlocal injected
        if getattr(statement, "is_update", False) and not injected:
            injected = True
            original_execute(
                update(Complaint)
                .where(Complaint.id == complaint.id)
                .values(status="resolved")
                .execution_options(synchronize_session=False)
            )
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(race_db, "execute", simulate_competing_write)

    payload = StaffComplaintStatusUpdate(
        status="in_progress",
        remark="Attempt based on outdated complaint status.",
    )

    with pytest.raises(HTTPException) as exc_info:
        update_department_complaint_status(
            race_db, staff, complaint.id, payload
        )

    assert injected
    assert exc_info.value.status_code == 409
    race_db.close()
    assert (
        db.query(ComplaintStatusHistory)
        .filter_by(complaint_id=complaint.id)
        .count()
        == 0
    )


def test_reopen_rejects_stale_reopen_count(
    db: Session, student_user, seeded_departments, monkeypatch
):
    """A stale reopen count must not produce another history event."""
    complaint = _create_complaint(
        db,
        student_id=student_user.id,
        department_id=seeded_departments["it"].id,
        status="resolved",
        resolved_at=datetime.now(timezone.utc) - timedelta(days=1),
        reopen_count=0,
    )

    race_db = Session(
        bind=db.connection(),
        join_transaction_mode="create_savepoint",
    )
    original_execute = race_db.execute
    injected = False

    def simulate_competing_write(statement, *args, **kwargs):
        nonlocal injected
        if getattr(statement, "is_update", False) and not injected:
            injected = True
            original_execute(
                update(Complaint)
                .where(Complaint.id == complaint.id)
                .values(reopen_count=1)
                .execution_options(synchronize_session=False)
            )
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(race_db, "execute", simulate_competing_write)

    with pytest.raises(HTTPException) as exc_info:
        reopen_student_complaint(
            race_db, student_user, complaint.id,
            remark="Attempt based on outdated reopen count.",
        )

    assert injected
    assert exc_info.value.status_code == 409
    race_db.close()
    assert (
        db.query(ComplaintStatusHistory)
        .filter_by(complaint_id=complaint.id)
        .count()
        == 0
    )
