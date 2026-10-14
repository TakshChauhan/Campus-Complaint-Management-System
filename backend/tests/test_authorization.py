def test_staff_cannot_create_complaint(client, staff_headers, seeded_departments):
    payload = {
        "title": "Staff trying to lodge complaint",
        "description": "This should be forbidden because complaints are student-only in Sprint 1.",
        "department_id": seeded_departments["it"].id,
    }
    response = client.post("/api/v1/complaints", json=payload, headers=staff_headers)
    assert response.status_code == 403
    assert "access denied" in response.json()["detail"].lower()


def test_admin_cannot_create_complaint(client, admin_headers, seeded_departments):
    payload = {
        "title": "Admin trying to lodge complaint",
        "description": "This should be forbidden because complaints are student-only in Sprint 1.",
        "department_id": seeded_departments["it"].id,
    }
    response = client.post("/api/v1/complaints", json=payload, headers=admin_headers)
    assert response.status_code == 403
    assert "access denied" in response.json()["detail"].lower()


def test_staff_cannot_view_student_complaint_history(client, staff_headers):
    response = client.get("/api/v1/complaints/mine", headers=staff_headers)
    assert response.status_code == 403


def test_admin_cannot_view_student_complaint_history(client, admin_headers):
    response = client.get("/api/v1/complaints/mine", headers=admin_headers)
    assert response.status_code == 403


def test_anonymous_user_denied_on_complaints(client):
    response = client.get("/api/v1/complaints/mine")
    assert response.status_code == 401


def test_staff_cannot_request_department_suggestions(client, staff_headers):
    payload = {
        "title": "Broken bench",
        "description": "The bench in the hallway is broken.",
    }
    response = client.post("/api/v1/departments/suggest", json=payload, headers=staff_headers)
    assert response.status_code == 403
    assert "access denied" in response.json()["detail"].lower()


def test_admin_cannot_request_department_suggestions(client, admin_headers):
    payload = {
        "title": "Broken bench",
        "description": "The bench in the hallway is broken.",
    }
    response = client.post("/api/v1/departments/suggest", json=payload, headers=admin_headers)
    assert response.status_code == 403
    assert "access denied" in response.json()["detail"].lower()

