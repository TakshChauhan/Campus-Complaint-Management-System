from app.models.user import User
from app.models.hmc_group import HMCGroup, HMCGroupWing
from app.models.building import Building
from datetime import datetime, timezone
from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.floor import Floor
from app.models.wing import Wing


def test_private_complaint_is_default(
    client, student_headers, seeded_departments, db
):
    response = client.post(
        "/api/v1/complaints",
        json={
            "title": "Hostel water issue",
            "description": "There is no water in the hostel bathroom.",
            "department_id": seeded_departments["hostel"].id,
        },
        headers=student_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()

    assert data["is_public"] is False
    assert data["hostel"] is None
    assert data["wing"] is None
    assert data["floor"] is None
    assert data["reopen_count"] == 0
    assert data["updated_at"] is not None
    assert data["resolved_at"] is None

    saved = db.get(Complaint, data["id"])
    assert saved.is_public is False

    history = db.query(ComplaintStatusHistory).filter_by(
        complaint_id=data["id"]
    ).all()
    assert len(history) == 1
    assert history[0].to_status == "submitted"


def test_public_complaint_with_hostel_location(client, student_headers, seeded_departments, db, student_user):
    admin = db.query(User).filter(
    User.role == "admin",
    User.is_active.is_(True),
    ).first()

    if admin is None:
     admin = User(
        name="Public Feed Test Admin",
        email="public-feed-test-admin@campus.edu",
        password_hash=None,
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    building = Building(name="Block B")
    db.add(building); db.flush()
    floor = Floor(name="2", building_id=building.id)
    wing = Wing(name="A", building_id=building.id)
    db.add_all([floor, wing]); db.flush()
    group = HMCGroup(name="Block B Floor 2 HMC", building_id=building.id, floor_id=floor.id)
    db.add(group); db.flush()
    db.add(HMCGroupWing(hmc_group_id=group.id, building_id=building.id, floor_id=floor.id, wing_id=wing.id))
    student_user.residence_building_id = building.id
    student_user.residence_floor_id = floor.id
    student_user.wing_id = wing.id
    student_user.residence_verified_at = datetime.now(timezone.utc)
    student_user.residence_verified_by_id = admin.id
    db.commit(); db.refresh(floor); db.refresh(wing)
    response = client.post("/api/v1/complaints", json={
        "title": "Broken hostel fan",
        "description": "The ceiling fan is not working properly.",
        "department_id": seeded_departments["hostel"].id,
        "is_public": True,
        "affected_building_id": building.id,
        "affected_floor_id": floor.id,
        "affected_wing_id": wing.id,
        "hostel": "  Block B  ", "wing": "  A  ", "floor": "  2  ",
    }, headers=student_headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["is_public"] is True
    assert data["hostel"] == "Block B"
    assert data["wing"] == "A" and data["floor"] == "2"
    assert data["affected_building_id"] == building.id
    assert data["visibility_scope"] == "hmc_group_public"
    assert data["feed_review_status"] == "auto_approved"
    assert data["publication_status"] == "published"
    saved = db.get(Complaint, data["id"])
    assert saved.affected_building_id == building.id
    assert saved.visibility_scope == "hmc_group_public"
    assert saved.publication_status == "published"
    detail = client.get(f"/api/v1/complaints/{data['id']}", headers=student_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["visibility_scope"] == "hmc_group_public"
    assert detail.json()["publication_status"] == "published"
    assert detail.json()["feed_review_status"] == "auto_approved"

def test_rejects_invalid_location_length(
    client, student_headers, seeded_departments
):
    response = client.post(
        "/api/v1/complaints",
        json={
            "title": "Hostel maintenance",
            "description": "Maintenance is needed in the hostel.",
            "department_id": seeded_departments["hostel"].id,
            "hostel": "A" * 101,
        },
        headers=student_headers,
    )

    assert response.status_code == 422


def test_other_student_cannot_view_private_complaint(
    client, student_headers, student_b_headers, seeded_departments
):
    created = client.post(
        "/api/v1/complaints",
        json={
            "title": "Private hostel issue",
            "description": "This complaint should remain private.",
            "department_id": seeded_departments["hostel"].id,
            "is_public": False,
        },
        headers=student_headers,
    )

    assert created.status_code == 201, created.text

    complaint_id = created.json()["id"]

    other_student = client.get(
        f"/api/v1/complaints/{complaint_id}",
        headers=student_b_headers,
    )

    assert other_student.status_code == 404
