from app.scripts.seed_departments import seed_departments
from app.models.department import Department


def test_list_departments_deterministic_active_only(client, student_headers, seeded_departments):
    response = client.get("/api/v1/departments", headers=student_headers)
    assert response.status_code == 200
    data = response.json()

    # Active departments were Hostel, IT Services, Library
    dept_names = [d["name"] for d in data]
    assert "Hostel" in dept_names
    assert "IT Services" in dept_names
    assert "Library" in dept_names

    # Inactive department "Printing Press (Archived)" MUST NOT be present
    assert "Printing Press (Archived)" not in dept_names

    # Check deterministic alphabetical ordering
    assert dept_names == sorted(dept_names)


def test_list_departments_unauthorized(client):
    response = client.get("/api/v1/departments")
    assert response.status_code == 401


def test_department_seed_is_idempotent(db):
    """Calling seed_departments multiple times must not create duplicate records."""
    # First run
    seed_departments(db)
    count_first = db.query(Department).count()

    # Second run
    seed_departments(db)
    count_second = db.query(Department).count()

    assert count_first == count_second
    assert count_first >= 6


def test_department_ai_suggestion_contract(client, student_headers, seeded_departments):
    payload = {
        "title": "Wi-Fi disconnected in hostel room",
        "description": "The campus internet and Wi-Fi connection keeps dropping every few minutes.",
    }
    response = client.post("/api/v1/departments/suggest", json=payload, headers=student_headers)
    assert response.status_code == 200
    data = response.json()

    assert "suggestions" in data
    assert "disclaimer" in data
    assert len(data["suggestions"]) > 0

    first_suggestion = data["suggestions"][0]
    assert "department_id" in first_suggestion
    assert "department_name" in first_suggestion
    assert 0.0 <= first_suggestion["confidence_score"] <= 1.0
    assert "rationale" in first_suggestion

def test_department_suggestion_mappings(client, student_headers, db):
    # Ensure departments are seeded for testing
    seed_departments(db)

    test_cases = [
        # Wi-Fi variants
        ("Wi-Fi issue in lab", "The campus Wi-Fi drops every 5 minutes", "IT Services"),
        ("Internet connection down", "The wi-fi and network are unreachable", "IT Services"),
        ("Ethernet and router failure", "Cannot access the student portal via lan", "IT Services"),
        # Clear department domains
        ("Hostel room issue", "Water leaking in washroom and tap broken", "Hostel"),
        ("Need to borrow a book", "The reading room is closed and catalog missing", "Library"),
        ("Bad food in canteen", "The dinner and breakfast meal was awful", "Mess & Cafeteria"),
        ("Broken badminton net", "The gymnasium court has broken cricket nets", "Sports & Gymnasium"),
        ("Gate entry issue", "The guard at main security gate stopped student entry", "Campus Security"),
        ("Fever and need medicines", "The clinic doctor is unavailable and need first aid", "Medical Facility"),
    ]

    for title, desc, expected_dept in test_cases:
        response = client.post(
            "/api/v1/departments/suggest",
            json={"title": title, "description": desc},
            headers=student_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "provisional_advisory"
        assert len(data["suggestions"]) > 0
        assert data["suggestions"][0]["department_name"] == expected_dept


def test_department_suggestion_security_context(client, student_headers, db):
    """Test campus security suggestion routing."""
    seed_departments(db)

    response_sec = client.post(
        "/api/v1/departments/suggest",
        json={
            "title": "Night patrol required near parking",
            "description": "Suspicious activity noticed, please send security guard and patrol.",
        },
        headers=student_headers,
    )
    assert response_sec.status_code == 200
    data_sec = response_sec.json()
    assert data_sec["suggestions"][0]["department_name"] == "Campus Security"


def test_department_suggestion_ambiguous_tied_candidates(client, student_headers, db):
    """When input has tied top scores across distinct departments,

    status should be 'uncertain' and suggestions should contain the tied candidates.
    """
    seed_departments(db)

    # 'badminton' matches Sports & Gym (1 keyword = 0.70)
    # 'wifi' matches IT Services (1 keyword = 0.70)
    payload = {
        "title": "Badminton wifi issue",
        "description": "Badminton and wifi connectivity problem.",
    }
    response = client.post("/api/v1/departments/suggest", json=payload, headers=student_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "uncertain"
    assert len(data["suggestions"]) >= 2
    top_scores = [s["confidence_score"] for s in data["suggestions"]]
    assert top_scores[0] == top_scores[1]


def test_department_suggestion_no_matches_uncertain(client, student_headers, db):
    """When input matches no known department keywords,

    status should be 'uncertain' with an empty suggestions list.
    """
    seed_departments(db)
    response = client.post(
        "/api/v1/departments/suggest",
        json={"title": "Hello world foo bar", "description": "Completely unrelated nonsense string zzzqqq."},
        headers=student_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "uncertain"
    assert len(data["suggestions"]) == 0


def test_department_suggestion_inactive_department_never_suggested(client, student_headers, seeded_departments):
    """Departments with is_active=False must never be returned in suggestions."""
    inactive = seeded_departments["inactive"]
    assert inactive.is_active is False

    response = client.post(
        "/api/v1/departments/suggest",
        json={"title": "Library books and quiet study", "description": "Legacy printing facility with books."},
        headers=student_headers,
    )
    assert response.status_code == 200
    data = response.json()
    suggested_ids = [s["department_id"] for s in data["suggestions"]]
    assert inactive.id not in suggested_ids



def test_department_suggestion_failure_fallback(client, student_headers, db, monkeypatch):
    """When suggestion service encounters an unhandled internal exception,

    it must return status='error_fallback' with empty suggestions rather than HTTP 500.
    """
    seed_departments(db)

    def mock_suggest(*args, **kwargs):
        raise Exception("Simulated classifier crash")

    from app.services.suggestion_service import SuggestionService
    monkeypatch.setattr(SuggestionService, "_heuristic_suggest", mock_suggest)

    response = client.post(
        "/api/v1/departments/suggest",
        json={"title": "Valid title", "description": "Valid description test text"},
        headers=student_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "error_fallback"
    assert len(response.json()["suggestions"]) == 0


def test_suggestion_failure_does_not_block_complaint_submission(client, student_headers, seeded_departments, monkeypatch):
    """Suggestion failure must NOT prevent a student from manually selecting a department

    and successfully submitting a complaint.
    """
    # 1. Suggestion fails
    def mock_suggest(*args, **kwargs):
        raise Exception("Simulated classifier crash")

    from app.services.suggestion_service import SuggestionService
    monkeypatch.setattr(SuggestionService, "_heuristic_suggest", mock_suggest)

    suggest_res = client.post(
        "/api/v1/departments/suggest",
        json={"title": "Broken washroom tap", "description": "Water leaking constantly in room."},
        headers=student_headers,
    )
    assert suggest_res.status_code == 200
    assert suggest_res.json()["status"] == "error_fallback"

    # 2. Student manually chooses Hostel department and submits complaint
    complaint_payload = {
        "title": "Broken washroom tap",
        "description": "Water leaking constantly in room.",
        "department_id": seeded_departments["hostel"].id,
    }
    complaint_res = client.post("/api/v1/complaints", json=complaint_payload, headers=student_headers)
    assert complaint_res.status_code == 201
    created_data = complaint_res.json()
    assert created_data["title"] == complaint_payload["title"]
    assert created_data["department_id"] == seeded_departments["hostel"].id
    assert created_data["status"] == "submitted"


def test_complaints_suggest_endpoint_matches_sprint1_spec(client, student_headers, seeded_departments):
    payload = {
        "title": "Wi-Fi disconnected in computer lab",
        "description": "The campus internet and Wi-Fi connection keeps dropping every few minutes.",
    }
    response = client.post("/api/v1/complaints/suggest", json=payload, headers=student_headers)
    assert response.status_code == 200
    data = response.json()
    assert "suggestions" in data
    assert len(data["suggestions"]) > 0
    assert data["suggestions"][0]["department_name"] == "IT Services"
    assert "confidence_score" in data["suggestions"][0]
    assert "disclaimer" in data


