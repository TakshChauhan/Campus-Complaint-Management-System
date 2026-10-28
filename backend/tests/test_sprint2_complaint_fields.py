from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory


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


def test_public_complaint_with_hostel_location(
    client, student_headers, seeded_departments, db
):
    response = client.post(
        "/api/v1/complaints",
        json={
            "title": "Broken hostel fan",
            "description": "The ceiling fan is not working properly.",
            "department_id": seeded_departments["hostel"].id,
            "is_public": True,
            "hostel": "  Block B  ",
            "wing": "  East Wing  ",
            "floor": "  2  ",
        },
        headers=student_headers,
    )

    assert response.status_code == 201, response.text
    data = response.json()

    assert data["is_public"] is True
    assert data["hostel"] == "Block B"
    assert data["wing"] == "East Wing"
    assert data["floor"] == "2"

    saved = db.get(Complaint, data["id"])
    assert saved.is_public is True
    assert saved.hostel == "Block B"
    assert saved.wing == "East Wing"
    assert saved.floor == "2"

    detail = client.get(
        f"/api/v1/complaints/{data['id']}",
        headers=student_headers,
    )

    assert detail.status_code == 200, detail.text
    assert detail.json()["is_public"] is True
    assert detail.json()["hostel"] == "Block B"


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
