from app.services.duplicate_service import find_similar


def test_duplicate_service_public_match():
    candidates = [
        {
            "id": 1,
            "title": "Wi-Fi down in Hostel C",
            "description": "Internet disconnected in hostel rooms",
            "department": "IT Support",
            "status": "submitted",
            "is_public": True,
            "user_id": 99,
        }
    ]

    # Lower threshold for short mock text phrases
    results = find_similar(
        title="Wi-Fi not working in Hostel C",
        description="No internet connection",
        candidate_complaints=candidates,
        current_student_id=101,
        threshold=0.30,
    )

    assert len(results) == 1
    assert results[0]["title"] == "Wi-Fi down in Hostel C"
    assert "user_id" not in results[0]
    assert "creator_name" not in results[0]


def test_duplicate_service_private_complaint_not_leaked():
    candidates = [
        {
            "id": 2,
            "title": "Gym AC not cooling",
            "description": "Air conditioner issue in gym",
            "department": "Sports",
            "status": "submitted",
            "is_public": False,
            "user_id": 88,  # Another student's private complaint
        }
    ]

    results = find_similar(
        title="Gym AC broken",
        description="Air conditioner issue",
        candidate_complaints=candidates,
        current_student_id=101,  # Different student ID
        threshold=0.10,
    )

    # Privacy constraint: private complaint of another user must never match
    assert len(results) == 0


def test_duplicate_service_own_private_complaint_allowed():
    candidates = [
        {
            "id": 3,
            "title": "Tap broken in washroom",
            "description": "Water leakage in washroom",
            "department": "Hostel",
            "status": "in_progress",
            "is_public": False,
            "user_id": 101,  # Matches current student
        }
    ]

    results = find_similar(
        title="Tap broken in washroom",
        description="Water leakage in washroom",
        candidate_complaints=candidates,
        current_student_id=101,
        threshold=0.50,
    )

    assert len(results) == 1
    assert results[0]["department"] == "Hostel"


def test_duplicate_service_safe_fallback_on_empty():
    results = find_similar("", "", [], current_student_id=101)
    assert results == []