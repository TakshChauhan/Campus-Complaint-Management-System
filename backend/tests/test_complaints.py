from app.models.complaint import Complaint


def test_create_complaint_success(client, db, student_user, student_headers, seeded_departments):
    target_dept = seeded_departments["it"]
    payload = {
        "title": "Wi-Fi not working in hostel",
        "description": "The Wi-Fi connection has been unavailable since this morning in block B.",
        "department_id": target_dept.id,
    }
    response = client.post("/api/v1/complaints", json=payload, headers=student_headers)
    assert response.status_code == 201
    data = response.json()

    assert data["id"] is not None
    assert data["title"] == payload["title"]
    assert data["description"] == payload["description"]
    assert data["department_id"] == target_dept.id
    assert data["department_name"] == target_dept.name
    assert data["created_by_id"] == student_user.id
    assert data["status"] == "submitted"
    assert data["created_at"] is not None

    # Verify genuine database persistence
    saved_complaint = db.query(Complaint).filter(Complaint.id == data["id"]).first()
    assert saved_complaint is not None
    assert saved_complaint.title == payload["title"]
    assert saved_complaint.created_by_id == student_user.id
    assert saved_complaint.status == "submitted"


def test_create_complaint_rejects_inactive_department(client, student_headers, seeded_departments):
    inactive_dept = seeded_departments["inactive"]
    payload = {
        "title": "Printing machine broken",
        "description": "The old printing machine in the basement is throwing paper jams constantly.",
        "department_id": inactive_dept.id,
    }
    response = client.post("/api/v1/complaints", json=payload, headers=student_headers)
    assert response.status_code == 400
    assert "inactive" in response.json()["detail"].lower()


def test_create_complaint_rejects_unknown_department(client, student_headers):
    payload = {
        "title": "Some random complaint",
        "description": "Detailed description that meets the minimum length requirement.",
        "department_id": 99999,  # does not exist
    }
    response = client.post("/api/v1/complaints", json=payload, headers=student_headers)
    assert response.status_code == 404
    assert "does not exist" in response.json()["detail"].lower()


def test_create_complaint_validation_title_too_short(client, student_headers, seeded_departments):
    payload = {
        "title": "Hi",  # < 3 characters
        "description": "Valid length description for testing validation rules.",
        "department_id": seeded_departments["it"].id,
    }
    response = client.post("/api/v1/complaints", json=payload, headers=student_headers)
    assert response.status_code == 422


def test_create_complaint_validation_title_whitespace_only(client, student_headers, seeded_departments):
    payload = {
        "title": "     ",
        "description": "Valid length description for testing validation rules.",
        "department_id": seeded_departments["it"].id,
    }
    response = client.post("/api/v1/complaints", json=payload, headers=student_headers)
    assert response.status_code == 422


def test_create_complaint_validation_description_too_short(client, student_headers, seeded_departments):
    payload = {
        "title": "Valid Title Here",
        "description": "Too short",  # < 10 characters
        "department_id": seeded_departments["it"].id,
    }
    response = client.post("/api/v1/complaints", json=payload, headers=student_headers)
    assert response.status_code == 422


def test_create_complaint_validation_invalid_department_id(client, student_headers):
    payload = {
        "title": "Valid Title Here",
        "description": "Valid description that meets minimum length.",
        "department_id": -5,  # <= 0
    }
    response = client.post("/api/v1/complaints", json=payload, headers=student_headers)
    assert response.status_code == 422


def test_complaints_mine_empty_history(client, student_headers):
    response = client.get("/api/v1/complaints/mine", headers=student_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_complaints_mine_isolation_between_students(
    client,
    student_headers,
    student_b_headers,
    seeded_departments
):
    dept_id = seeded_departments["it"].id

    # Student Alice creates a complaint
    client.post(
        "/api/v1/complaints",
        json={
            "title": "Alice Complaint 1",
            "description": "Alice lodged this complaint about campus IT.",
            "department_id": dept_id,
        },
        headers=student_headers,
    )

    # Student Bob creates a complaint
    client.post(
        "/api/v1/complaints",
        json={
            "title": "Bob Complaint 1",
            "description": "Bob lodged this complaint about campus IT.",
            "department_id": dept_id,
        },
        headers=student_b_headers,
    )

    # Alice queries own complaints
    res_alice = client.get("/api/v1/complaints/mine", headers=student_headers)
    assert res_alice.status_code == 200
    alice_titles = [c["title"] for c in res_alice.json()]
    assert "Alice Complaint 1" in alice_titles
    assert "Bob Complaint 1" not in alice_titles

    # Bob queries own complaints
    res_bob = client.get("/api/v1/complaints/mine", headers=student_b_headers)
    assert res_bob.status_code == 200
    bob_titles = [c["title"] for c in res_bob.json()]
    assert "Bob Complaint 1" in bob_titles
    assert "Alice Complaint 1" not in bob_titles


def test_complaints_mine_ordering_newest_first(client, student_headers, seeded_departments):
    dept_id = seeded_departments["it"].id

    client.post(
        "/api/v1/complaints",
        json={"title": "Complaint Earliest", "description": "First complaint description here.", "department_id": dept_id},
        headers=student_headers,
    )
    client.post(
        "/api/v1/complaints",
        json={"title": "Complaint Middle", "description": "Second complaint description here.", "department_id": dept_id},
        headers=student_headers,
    )
    client.post(
        "/api/v1/complaints",
        json={"title": "Complaint Latest", "description": "Third complaint description here.", "department_id": dept_id},
        headers=student_headers,
    )

    response = client.get("/api/v1/complaints/mine", headers=student_headers)
    assert response.status_code == 200
    titles = [c["title"] for c in response.json()]
    assert titles == ["Complaint Latest", "Complaint Middle", "Complaint Earliest"]


def test_create_complaint_validation_title_too_long(client, student_headers, seeded_departments):
    payload = {
        "title": "A" * 121,  # > 120 characters
        "description": "Valid length description for testing validation rules.",
        "department_id": seeded_departments["it"].id,
    }
    response = client.post("/api/v1/complaints", json=payload, headers=student_headers)
    assert response.status_code == 422


def test_create_complaint_validation_description_too_long(client, student_headers, seeded_departments):
    payload = {
        "title": "Valid Complaint Title",
        "description": "B" * 2001,  # > 2000 characters
        "department_id": seeded_departments["it"].id,
    }
    response = client.post("/api/v1/complaints", json=payload, headers=student_headers)
    assert response.status_code == 422


def test_complaint_persistence_across_separate_session(client, student_headers, seeded_departments, db):
    dept_id = seeded_departments["it"].id
    res = client.post(
        "/api/v1/complaints",
        json={"title": "Persistent Complaint", "description": "This complaint tests DB persistence.", "department_id": dept_id},
        headers=student_headers,
    )
    assert res.status_code == 201
    complaint_id = res.json()["id"]

    # Verify query through database session
    db.expire_all()
    record = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    assert record is not None
    assert record.title == "Persistent Complaint"


def test_complaints_mine_pagination(client, student_headers, seeded_departments):
    """Verify limit and offset pagination on /api/v1/complaints/mine."""
    dept_id = seeded_departments["it"].id

    for i in range(5):
        client.post(
            "/api/v1/complaints",
            json={
                "title": f"Numbered Complaint {i}",
                "description": f"Description for numbered complaint {i} with sufficient length.",
                "department_id": dept_id,
            },
            headers=student_headers,
        )

    # First page: limit 2, offset 0 -> newest 2 (Numbered Complaint 4, 3)
    res_page1 = client.get("/api/v1/complaints/mine?limit=2&offset=0", headers=student_headers)
    assert res_page1.status_code == 200
    data1 = res_page1.json()
    assert len(data1) == 2
    assert data1[0]["title"] == "Numbered Complaint 4"
    assert data1[1]["title"] == "Numbered Complaint 3"

    # Second page: limit 2, offset 2 -> next 2 (Numbered Complaint 2, 1)
    res_page2 = client.get("/api/v1/complaints/mine?limit=2&offset=2", headers=student_headers)
    assert res_page2.status_code == 200
    data2 = res_page2.json()
    assert len(data2) == 2
    assert data2[0]["title"] == "Numbered Complaint 2"
    assert data2[1]["title"] == "Numbered Complaint 1"

    # Third page: limit 2, offset 4 -> remaining 1 (Numbered Complaint 0)
    res_page3 = client.get("/api/v1/complaints/mine?limit=2&offset=4", headers=student_headers)
    assert res_page3.status_code == 200
    data3 = res_page3.json()
    assert len(data3) == 1
    assert data3[0]["title"] == "Numbered Complaint 0"


def test_complaints_mine_pagination_validation(client, student_headers):
    """Validation rejects limit < 1, limit > 100, and negative offset."""
    # limit > 100
    r1 = client.get("/api/v1/complaints/mine?limit=101", headers=student_headers)
    assert r1.status_code == 422

    # limit < 1
    r2 = client.get("/api/v1/complaints/mine?limit=0", headers=student_headers)
    assert r2.status_code == 422

    # negative offset
    r3 = client.get("/api/v1/complaints/mine?offset=-1", headers=student_headers)
    assert r3.status_code == 422


def test_complaint_stores_script_tags_as_inert_data(client, student_headers, seeded_departments):
    """Strings such as <script>alert(1)</script> are stored and returned as inert data."""
    dept_id = seeded_departments["it"].id
    script_payload = {
        "title": "<script>alert('xss')</script>",
        "description": "<img src=x onerror=alert(1)> description with sufficient length.",
        "department_id": dept_id,
    }
    res = client.post("/api/v1/complaints", json=script_payload, headers=student_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "<script>alert('xss')</script>"
    assert data["description"] == "<img src=x onerror=alert(1)> description with sufficient length."

