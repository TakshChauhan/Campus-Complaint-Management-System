
"""HTTP integration tests for duplicate suggestions."""

from datetime import datetime, timezone

from app.models.complaint import Complaint
from app.models.hostel import Hostel
from app.models.hostel_wing import HostelWing
from app.models.hostel_floor import HostelFloor
from app.models.student_residence import StudentResidence


URL = "/api/v1/complaints/duplicate-suggestions"

DRAFT = {
    "title": "Hostel wifi router broken",
    "description": "The hostel wifi router is broken and internet is unavailable.",
}


def _create_verified_residence(db, student, verifier):
    """Create an active hostel hierarchy and a verified student residence."""
    hostel = Hostel(
        code="TEST_HOSTEL",
        name="Test Hostel",
        is_active=True,
    )
    db.add(hostel)
    db.flush()

    wing = HostelWing(
        hostel_id=hostel.id,
        code="A",
        name="Wing A",
        is_active=True,
    )
    db.add(wing)
    db.flush()

    floor = HostelFloor(
        wing_id=wing.id,
        code="F1",
        name="Floor 1",
        is_active=True,
    )
    db.add(floor)
    db.flush()

    residence = StudentResidence(
        student_id=student.id,
        floor_id=floor.id,
        status="verified",
        verified_by_id=verifier.id,
        verified_at=datetime.now(timezone.utc),
    )
    db.add(residence)
    db.flush()

    return floor


def test_duplicate_endpoint_requires_student(
    client, staff_headers, admin_headers
):
    assert client.post(URL, json=DRAFT).status_code == 401
    assert client.post(
        URL, json=DRAFT, headers=staff_headers
    ).status_code == 403
    assert client.post(
        URL, json=DRAFT, headers=admin_headers
    ).status_code == 403


def test_duplicate_endpoint_validates_input(client, student_headers):
    response = client.post(
        URL,
        json={"title": "Hi", "description": "short"},
        headers=student_headers,
    )
    assert response.status_code == 422


def test_duplicate_endpoint_returns_public_match(
    client, db, seeded_departments,
    student_user, student_b_user, student_headers
):
    floor = _create_verified_residence(db, student_user, student_b_user)

    public = Complaint(
        title=DRAFT["title"],
        description=DRAFT["description"],
        department_id=seeded_departments["hostel"].id,
        created_by_id=student_b_user.id,
        status="submitted",
        is_public=True,
        floor_id=floor.id,
    )
    db.add(public)
    db.commit()

    response = client.post(URL, json=DRAFT, headers=student_headers)

    assert response.status_code == 200, response.text
    data = response.json()

    assert len(data["matches"]) == 1
    match = data["matches"][0]
    assert match["id"] == public.id
    assert match["similarity_score"] > 0
    assert "created_by_id" not in match
    assert "student_id" not in match
    assert "email" not in match


def test_duplicate_endpoint_hides_other_private_complaints(
    client, db, seeded_departments,
    student_user, student_b_user, student_headers
):
    floor = _create_verified_residence(db, student_user, student_b_user)

    other_private = Complaint(
        title=DRAFT["title"],
        description=DRAFT["description"],
        department_id=seeded_departments["hostel"].id,
        created_by_id=student_b_user.id,
        status="submitted",
        is_public=False,
        floor_id=floor.id,
    )
    db.add(other_private)
    db.commit()

    response = client.post(URL, json=DRAFT, headers=student_headers)

    assert response.status_code == 200, response.text
    assert response.json()["matches"] == []


def test_duplicate_endpoint_includes_own_private_complaint(
    client, db, seeded_departments,
    student_user, student_b_user, student_headers
):
    floor = _create_verified_residence(db, student_user, student_b_user)

    own_private = Complaint(
        title=DRAFT["title"],
        description=DRAFT["description"],
        department_id=seeded_departments["hostel"].id,
        created_by_id=student_user.id,
        status="submitted",
        is_public=False,
        floor_id=floor.id,
    )
    db.add(own_private)
    db.commit()

    response = client.post(URL, json=DRAFT, headers=student_headers)

    assert response.status_code == 200, response.text
    matches = response.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["id"] == own_private.id


def test_duplicate_endpoint_returns_no_matches_without_verified_residence(
    client, db, seeded_departments,
    student_user, student_b_user, student_headers
):
    # A public complaint alone must not bypass residence verification.
    public = Complaint(
        title=DRAFT["title"],
        description=DRAFT["description"],
        department_id=seeded_departments["hostel"].id,
        created_by_id=student_b_user.id,
        status="submitted",
        is_public=True,
    )
    db.add(public)
    db.commit()

    response = client.post(URL, json=DRAFT, headers=student_headers)

    assert response.status_code == 200, response.text
    assert response.json()["matches"] == []
