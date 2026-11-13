"""Tests for S4-04: Hostel-scoped Staff Access.

Verifies that Hostel department staff access is restricted according to their assigned hostels on:
1. Complaint queue (`GET /api/v1/staff/complaints`)
2. Complaint detail (`GET /api/v1/staff/complaints/{id}`)
3. Complaint status updates (`PATCH /api/v1/staff/complaints/{id}/status`)
4. Complaint status history (`GET /api/v1/complaints/{id}/history`)
5. Residence queue (`GET /api/v1/staff/residences`)
6. Residence decisions (`POST /api/v1/staff/residences/{id}/decision`)

Crucial security requirement: Out-of-scope resources must return 404 Not Found, never 403.
Preserves admin access and existing behavior for non-Hostel departments.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.student_residence import StudentResidence
from app.models.user import User


def _auth_headers(user: User) -> dict:
    token = create_access_token(
        subject=str(user.id),
        claims={"role": user.role, "email": user.email},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def scoped_world(db: Session, seeded_departments: dict):
    hostel_dept = seeded_departments["hostel"]
    it_dept = seeded_departments["it"]

    # 1. Hostels
    hostel_a = Hostel(code="HSA", name="Hostel SA", is_active=True)
    hostel_b = Hostel(code="HSB", name="Hostel SB", is_active=True)
    db.add_all([hostel_a, hostel_b])
    db.flush()

    # 2. Wings
    wing_a = HostelWing(hostel_id=hostel_a.id, code="WSA", name="Wing SA", is_active=True)
    wing_b = HostelWing(hostel_id=hostel_b.id, code="WSB", name="Wing SB", is_active=True)
    db.add_all([wing_a, wing_b])
    db.flush()

    # 3. Floors
    floor_a = HostelFloor(wing_id=wing_a.id, code="FSA1", name="Floor SA1", is_active=True)
    floor_b = HostelFloor(wing_id=wing_b.id, code="FSB1", name="Floor SB1", is_active=True)
    db.add_all([floor_a, floor_b])
    db.flush()

    # 4. Users
    admin = User(name="Admin Super", email="admin.s4@campus.edu", role="admin", is_active=True)
    student = User(name="Student S4", email="student.s4@student.campus.edu", role="student", is_active=True)
    staff_a = User(name="Staff Hostel A", email="staff.a@campus.edu", role="staff", department_id=hostel_dept.id, is_active=True)
    staff_b = User(name="Staff Hostel B", email="staff.b@campus.edu", role="staff", department_id=hostel_dept.id, is_active=True)
    staff_none = User(name="Staff No Hostel", email="staff.none@campus.edu", role="staff", department_id=hostel_dept.id, is_active=True)
    it_staff = User(name="Staff IT", email="staff.it@campus.edu", role="staff", department_id=it_dept.id, is_active=True)
    db.add_all([admin, student, staff_a, staff_b, staff_none, it_staff])
    db.flush()

    # 5. Assignments: staff_a -> hostel_a, staff_b -> hostel_b, staff_none -> none
    assign_a = StaffHostelAssignment(user_id=staff_a.id, hostel_id=hostel_a.id, assigned_by_id=admin.id)
    assign_b = StaffHostelAssignment(user_id=staff_b.id, hostel_id=hostel_b.id, assigned_by_id=admin.id)
    db.add_all([assign_a, assign_b])
    db.flush()

    # 6. Complaints: Complaint A in Hostel A, Complaint B in Hostel B, Complaint IT in IT dept
    comp_a = Complaint(
        title="Tap broken in Hostel A",
        description="Leaking pipe in bathroom",
        department_id=hostel_dept.id,
        created_by_id=student.id,
        floor_id=floor_a.id,
        status="submitted",
    )
    comp_b = Complaint(
        title="Fan broken in Hostel B",
        description="Ceiling fan motor burned",
        department_id=hostel_dept.id,
        created_by_id=student.id,
        floor_id=floor_b.id,
        status="submitted",
    )
    comp_it = Complaint(
        title="Internet router down",
        description="Wi-Fi connectivity failure",
        department_id=it_dept.id,
        created_by_id=student.id,
        floor_id=None,
        status="submitted",
    )
    db.add_all([comp_a, comp_b, comp_it])
    db.flush()

    # Add history event for comp_a and comp_b
    hist_a = ComplaintStatusHistory(
        complaint_id=comp_a.id,
        actor_id=student.id,
        from_status=None,
        to_status="submitted",
        remark="Initial lodging",
        created_at=datetime.now(timezone.utc),
    )
    hist_b = ComplaintStatusHistory(
        complaint_id=comp_b.id,
        actor_id=student.id,
        from_status=None,
        to_status="submitted",
        remark="Initial lodging",
        created_at=datetime.now(timezone.utc),
    )
    db.add_all([hist_a, hist_b])
    db.flush()

    # 7. Student Residences: Residence A on Floor A, Residence B on Floor B
    res_a = StudentResidence(
        student_id=student.id,
        floor_id=floor_a.id,
        status="pending",
    )
    # create second student for residence b
    student_2 = User(name="Student 2 S4", email="student2.s4@student.campus.edu", role="student", is_active=True)
    db.add(student_2)
    db.flush()
    res_b = StudentResidence(
        student_id=student_2.id,
        floor_id=floor_b.id,
        status="pending",
    )
    db.add_all([res_a, res_b])
    db.commit()

    return {
        "hostels": {"a": hostel_a, "b": hostel_b},
        "users": {
            "admin": admin,
            "student": student,
            "staff_a": staff_a,
            "staff_b": staff_b,
            "staff_none": staff_none,
            "it_staff": it_staff,
        },
        "complaints": {"a": comp_a, "b": comp_b, "it": comp_it},
        "residences": {"a": res_a, "b": res_b},
    }


def test_complaint_queue_scoped_to_assigned_hostel(client: TestClient, scoped_world: dict):
    """GET /api/v1/staff/complaints returns only complaints within the staff member's assigned hostels."""
    staff_a = scoped_world["users"]["staff_a"]
    comp_a = scoped_world["complaints"]["a"]
    comp_b = scoped_world["complaints"]["b"]

    resp = client.get("/api/v1/staff/complaints", headers=_auth_headers(staff_a))
    assert resp.status_code == 200
    items = resp.json()
    item_ids = [item["id"] for item in items]
    assert comp_a.id in item_ids
    assert comp_b.id not in item_ids


def test_complaint_queue_hostel_filter_param_out_of_scope_returns_empty(client: TestClient, scoped_world: dict):
    """GET /api/v1/staff/complaints?hostel_id=... for out-of-scope hostel returns empty list."""
    staff_a = scoped_world["users"]["staff_a"]
    hostel_b = scoped_world["hostels"]["b"]

    resp = client.get(f"/api/v1/staff/complaints?hostel_id={hostel_b.id}", headers=_auth_headers(staff_a))
    assert resp.status_code == 200
    assert resp.json() == []
    assert resp.headers.get("X-Total-Count") == "0"


def test_complaint_queue_unassigned_hostel_staff_returns_empty(client: TestClient, scoped_world: dict):
    """GET /api/v1/staff/complaints for Hostel staff with 0 assignments returns empty list."""
    staff_none = scoped_world["users"]["staff_none"]

    resp = client.get("/api/v1/staff/complaints", headers=_auth_headers(staff_none))
    assert resp.status_code == 200
    assert resp.json() == []


def test_complaint_queue_non_hostel_staff_unaffected(client: TestClient, scoped_world: dict):
    """GET /api/v1/staff/complaints for IT staff returns IT complaints unrestricted by hostel scoping."""
    it_staff = scoped_world["users"]["it_staff"]
    comp_it = scoped_world["complaints"]["it"]

    resp = client.get("/api/v1/staff/complaints", headers=_auth_headers(it_staff))
    assert resp.status_code == 200
    item_ids = [item["id"] for item in resp.json()]
    assert comp_it.id in item_ids


def test_complaint_detail_in_scope_succeeds_and_out_of_scope_returns_404(client: TestClient, scoped_world: dict):
    """GET /api/v1/staff/complaints/{id} returns 200 for assigned hostel and 404 for other hostels."""
    staff_a = scoped_world["users"]["staff_a"]
    comp_a = scoped_world["complaints"]["a"]
    comp_b = scoped_world["complaints"]["b"]

    # In-scope: 200 OK
    resp_in = client.get(f"/api/v1/staff/complaints/{comp_a.id}", headers=_auth_headers(staff_a))
    assert resp_in.status_code == 200
    assert resp_in.json()["id"] == comp_a.id

    # Out-of-scope: MUST return 404 Not Found, NEVER 403
    resp_out = client.get(f"/api/v1/staff/complaints/{comp_b.id}", headers=_auth_headers(staff_a))
    assert resp_out.status_code == 404
    assert resp_out.json()["detail"] == "Complaint not found."


def test_complaint_detail_unassigned_hostel_staff_returns_404(client: TestClient, scoped_world: dict):
    """GET /api/v1/staff/complaints/{id} returns 404 for unassigned hostel staff."""
    staff_none = scoped_world["users"]["staff_none"]
    comp_a = scoped_world["complaints"]["a"]

    resp = client.get(f"/api/v1/staff/complaints/{comp_a.id}", headers=_auth_headers(staff_none))
    assert resp.status_code == 404


def test_complaint_status_update_out_of_scope_returns_404(client: TestClient, scoped_world: dict):
    """PATCH /api/v1/staff/complaints/{id}/status returns 404 for out-of-scope complaints."""
    staff_a = scoped_world["users"]["staff_a"]
    comp_b = scoped_world["complaints"]["b"]

    payload = {"status": "in_progress", "remark": "Attempting unauthorized update"}
    resp = client.patch(
        f"/api/v1/staff/complaints/{comp_b.id}/status",
        json=payload,
        headers=_auth_headers(staff_a),
    )
    # Must return 404 Not Found, never 403
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Complaint not found."


def test_complaint_status_update_in_scope_succeeds(client: TestClient, scoped_world: dict):
    """PATCH /api/v1/staff/complaints/{id}/status succeeds for in-scope complaints."""
    staff_a = scoped_world["users"]["staff_a"]
    comp_a = scoped_world["complaints"]["a"]

    payload = {"status": "in_progress", "remark": "Investigating hostel A tap"}
    resp = client.patch(
        f"/api/v1/staff/complaints/{comp_a.id}/status",
        json=payload,
        headers=_auth_headers(staff_a),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


def test_complaint_history_out_of_scope_returns_404(client: TestClient, scoped_world: dict):
    """GET /api/v1/complaints/{id}/history returns 404 for out-of-scope complaints."""
    staff_a = scoped_world["users"]["staff_a"]
    comp_b = scoped_world["complaints"]["b"]

    resp = client.get(
        f"/api/v1/complaints/{comp_b.id}/history",
        headers=_auth_headers(staff_a),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Complaint not found."


def test_complaint_history_in_scope_succeeds(client: TestClient, scoped_world: dict):
    """GET /api/v1/complaints/{id}/history succeeds for in-scope complaints."""
    staff_a = scoped_world["users"]["staff_a"]
    comp_a = scoped_world["complaints"]["a"]

    resp = client.get(
        f"/api/v1/complaints/{comp_a.id}/history",
        headers=_auth_headers(staff_a),
    )
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 1


def test_residence_queue_scoped_to_assigned_hostels(client: TestClient, scoped_world: dict):
    """GET /api/v1/staff/residences lists only residences from the staff member's assigned hostels."""
    staff_a = scoped_world["users"]["staff_a"]
    res_a = scoped_world["residences"]["a"]
    res_b = scoped_world["residences"]["b"]

    resp = client.get("/api/v1/staff/residences", headers=_auth_headers(staff_a))
    assert resp.status_code == 200
    items = resp.json()
    item_ids = [item["id"] for item in items]
    assert res_a.id in item_ids
    assert res_b.id not in item_ids


def test_residence_queue_unassigned_hostel_staff_returns_empty(client: TestClient, scoped_world: dict):
    """GET /api/v1/staff/residences returns empty list for unassigned hostel staff."""
    staff_none = scoped_world["users"]["staff_none"]

    resp = client.get("/api/v1/staff/residences", headers=_auth_headers(staff_none))
    assert resp.status_code == 200
    assert resp.json() == []


def test_residence_queue_admin_unrestricted(client: TestClient, scoped_world: dict):
    """GET /api/v1/staff/residences for admin returns all pending residences across all hostels."""
    admin = scoped_world["users"]["admin"]
    res_a = scoped_world["residences"]["a"]
    res_b = scoped_world["residences"]["b"]

    resp = client.get("/api/v1/staff/residences", headers=_auth_headers(admin))
    assert resp.status_code == 200
    item_ids = [item["id"] for item in resp.json()]
    assert res_a.id in item_ids
    assert res_b.id in item_ids


def test_residence_decision_out_of_scope_returns_404(client: TestClient, scoped_world: dict):
    """POST /api/v1/staff/residences/{id}/decision returns 404 for out-of-scope residence."""
    staff_a = scoped_world["users"]["staff_a"]
    res_b = scoped_world["residences"]["b"]

    payload = {"decision": "approve", "remark": "Approved"}
    resp = client.post(
        f"/api/v1/staff/residences/{res_b.id}/decision",
        json=payload,
        headers=_auth_headers(staff_a),
    )
    # Crucial security rule: Must return 404 Not Found, never 403
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Residence not found."


def test_residence_decision_in_scope_succeeds(client: TestClient, scoped_world: dict):
    """POST /api/v1/staff/residences/{id}/decision succeeds for in-scope residence."""
    staff_a = scoped_world["users"]["staff_a"]
    res_a = scoped_world["residences"]["a"]

    payload = {"decision": "approve", "remark": "Room verified"}
    resp = client.post(
        f"/api/v1/staff/residences/{res_a.id}/decision",
        json=payload,
        headers=_auth_headers(staff_a),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "verified"


# =========================================================================== #
# Issue #95: Legacy Text Location Security and Fail-Closed Regressions
# =========================================================================== #

@pytest.fixture
def legacy_text_world(db: Session, scoped_world: dict, seeded_departments: dict):
    """Seed legacy complaints with missing, empty, wrong, ambiguous, and conflicting hostel text."""
    hostel_dept = seeded_departments["hostel"]
    student = scoped_world["users"]["student"]
    floor_b_id = scoped_world["complaints"]["b"].floor_id

    def _create(title: str, floor_id=None, hostel=None):
        c = Complaint(
            title=title,
            description="Legacy complaint description for Issue #95 security testing.",
            department_id=hostel_dept.id,
            created_by_id=student.id,
            floor_id=floor_id,
            hostel=hostel,
            status="submitted",
        )
        db.add(c)
        db.flush()
        h = ComplaintStatusHistory(
            complaint_id=c.id,
            from_status=None,
            to_status="submitted",
            actor_id=student.id,
            remark="Submitted",
        )
        db.add(h)
        db.flush()
        return c

    complaints = {
        # Missing text: floor_id is None, hostel is None
        "missing": _create("Legacy missing hostel text", floor_id=None, hostel=None),
        # Empty string text: floor_id is None, hostel is ""
        "empty": _create("Legacy empty hostel text", floor_id=None, hostel=""),
        # Wrong hostel text: floor_id is None, hostel is "Hostel SB" (belongs to B, tested against A)
        "wrong": _create("Legacy wrong hostel text", floor_id=None, hostel="Hostel SB"),
        # Ambiguous / unrecognized text: floor_id is None, hostel is not an active hostel
        "ambiguous": _create("Legacy ambiguous hostel text", floor_id=None, hostel="Unknown Wing / Ambiguous Block"),
        # Casing mismatch: floor_id is None, hostel is "hostel sa" (must fail closed)
        "casing": _create("Legacy lowercase hostel text", floor_id=None, hostel="hostel sa"),
        # Valid exact match: floor_id is None, hostel is "Hostel SA" (matches Staff A's assignment)
        "valid_a": _create("Legacy valid hostel text A", floor_id=None, hostel="Hostel SA"),
        # Conflicting text: floor_id is in Hostel SB, but text claims "Hostel SA"
        "conflict": _create("Conflicting floor B with text A", floor_id=floor_b_id, hostel="Hostel SA"),
    }
    db.commit()
    for c in complaints.values():
        db.refresh(c)
    return complaints


def test_legacy_complaints_queue_excludes_unverified_hostel_text(
    client: TestClient, scoped_world: dict, legacy_text_world: dict
):
    """GET /api/v1/staff/complaints excludes complaints with missing, wrong, ambiguous, or casing-mismatched text."""
    staff_a = scoped_world["users"]["staff_a"]
    resp = client.get("/api/v1/staff/complaints", headers=_auth_headers(staff_a))
    assert resp.status_code == 200
    item_ids = {item["id"] for item in resp.json()}

    # Valid exact match for assigned Hostel SA is included
    assert legacy_text_world["valid_a"].id in item_ids

    # Unverified, missing, wrong, or ambiguous text MUST be excluded
    assert legacy_text_world["missing"].id not in item_ids
    assert legacy_text_world["empty"].id not in item_ids
    assert legacy_text_world["wrong"].id not in item_ids
    assert legacy_text_world["ambiguous"].id not in item_ids
    assert legacy_text_world["casing"].id not in item_ids

    # Conflicting complaint (canonical floor in Hostel B, text claims A) MUST be excluded from Staff A
    assert legacy_text_world["conflict"].id not in item_ids

    # Staff B (assigned to Hostel SB) sees the complaint with text "Hostel SB" and the canonical floor B complaint
    staff_b = scoped_world["users"]["staff_b"]
    resp_b = client.get("/api/v1/staff/complaints", headers=_auth_headers(staff_b))
    assert resp_b.status_code == 200
    b_item_ids = {item["id"] for item in resp_b.json()}
    assert legacy_text_world["wrong"].id in b_item_ids
    assert legacy_text_world["conflict"].id in b_item_ids
    assert legacy_text_world["valid_a"].id not in b_item_ids


def test_legacy_complaints_detail_returns_404_for_unverified_hostel_text(
    client: TestClient, scoped_world: dict, legacy_text_world: dict
):
    """GET /api/v1/staff/complaints/{id} returns 404 for complaints with missing, wrong, or ambiguous hostel text."""
    staff_a = scoped_world["users"]["staff_a"]

    # Missing, empty, wrong, ambiguous, casing-mismatched, and conflict complaints return 404
    for key in ("missing", "empty", "wrong", "ambiguous", "casing", "conflict"):
        c = legacy_text_world[key]
        resp = client.get(f"/api/v1/staff/complaints/{c.id}", headers=_auth_headers(staff_a))
        assert resp.status_code == 404, f"Expected 404 for '{key}', got {resp.status_code}"
        assert resp.json()["detail"] == "Complaint not found."

    # Valid exact match succeeds (200)
    valid_c = legacy_text_world["valid_a"]
    resp_valid = client.get(f"/api/v1/staff/complaints/{valid_c.id}", headers=_auth_headers(staff_a))
    assert resp_valid.status_code == 200
    assert resp_valid.json()["id"] == valid_c.id


def test_legacy_complaints_status_update_returns_404_for_unverified_hostel_text(
    client: TestClient, scoped_world: dict, legacy_text_world: dict
):
    """PATCH /api/v1/staff/complaints/{id}/status returns 404 and prevents mutation on unverified hostel text."""
    staff_a = scoped_world["users"]["staff_a"]
    payload = {"status": "in_progress", "remark": "Attempted update"}

    # Attempting to mutate missing, empty, wrong, ambiguous, casing-mismatched, or conflict complaints returns 404
    for key in ("missing", "empty", "wrong", "ambiguous", "casing", "conflict"):
        c = legacy_text_world[key]
        resp = client.patch(
            f"/api/v1/staff/complaints/{c.id}/status",
            json=payload,
            headers=_auth_headers(staff_a),
        )
        assert resp.status_code == 404, f"Expected 404 for '{key}', got {resp.status_code}"
        assert resp.json()["detail"] == "Complaint not found."

    # Valid exact match succeeds (200)
    valid_c = legacy_text_world["valid_a"]
    resp_valid = client.patch(
        f"/api/v1/staff/complaints/{valid_c.id}/status",
        json={"status": "in_progress", "remark": "Legitimate progress on Hostel SA legacy complaint"},
        headers=_auth_headers(staff_a),
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json()["status"] == "in_progress"


def test_legacy_complaints_history_returns_404_for_unverified_hostel_text(
    client: TestClient, scoped_world: dict, legacy_text_world: dict
):
    """GET /api/v1/complaints/{id}/history returns 404 for complaints with missing, wrong, or ambiguous hostel text."""
    staff_a = scoped_world["users"]["staff_a"]

    # History queries on missing, empty, wrong, ambiguous, casing-mismatched, or conflict complaints return 404
    for key in ("missing", "empty", "wrong", "ambiguous", "casing", "conflict"):
        c = legacy_text_world[key]
        resp = client.get(
            f"/api/v1/complaints/{c.id}/history",
            headers=_auth_headers(staff_a),
        )
        assert resp.status_code == 404, f"Expected 404 for '{key}', got {resp.status_code}"
        assert resp.json()["detail"] == "Complaint not found."

    # Valid exact match succeeds (200)
    valid_c = legacy_text_world["valid_a"]
    resp_valid = client.get(
        f"/api/v1/complaints/{valid_c.id}/history",
        headers=_auth_headers(staff_a),
    )
    assert resp_valid.status_code == 200
    assert len(resp_valid.json()) >= 1


def test_canonical_floor_strictly_overrides_conflicting_free_text(
    client: TestClient, scoped_world: dict, legacy_text_world: dict
):
    """Canonical floor mapping is strictly authoritative: free-text cannot bypass or override canonical floor."""
    conflict_c = legacy_text_world["conflict"]  # canonical floor_id is in Hostel SB, free-text hostel="Hostel SA"
    staff_a = scoped_world["users"]["staff_a"]  # assigned to Hostel SA
    staff_b = scoped_world["users"]["staff_b"]  # assigned to Hostel SB

    # Staff A cannot view or mutate conflict_c despite free-text saying "Hostel SA"
    resp_a_detail = client.get(f"/api/v1/staff/complaints/{conflict_c.id}", headers=_auth_headers(staff_a))
    assert resp_a_detail.status_code == 404

    resp_a_patch = client.patch(
        f"/api/v1/staff/complaints/{conflict_c.id}/status",
        json={"status": "in_progress", "remark": "Hacker attempt"},
        headers=_auth_headers(staff_a),
    )
    assert resp_a_patch.status_code == 404

    # Staff B can view and mutate conflict_c because canonical floor is in Hostel SB
    resp_b_detail = client.get(f"/api/v1/staff/complaints/{conflict_c.id}", headers=_auth_headers(staff_b))
    assert resp_b_detail.status_code == 200
    assert resp_b_detail.json()["id"] == conflict_c.id

    resp_b_patch = client.patch(
        f"/api/v1/staff/complaints/{conflict_c.id}/status",
        json={"status": "in_progress", "remark": "Legitimate update by Hostel SB staff"},
        headers=_auth_headers(staff_b),
    )
    assert resp_b_patch.status_code == 200
    assert resp_b_patch.json()["status"] == "in_progress"

