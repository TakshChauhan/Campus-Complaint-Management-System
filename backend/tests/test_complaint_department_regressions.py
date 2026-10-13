"""Member 3: Sprint 1 complaint / department API regression coverage.

All tests use the existing FastAPI TestClient and isolated in-memory SQLite
fixtures. No live Supabase or Google OAuth credentials are required.
"""

import pytest
from app.models.complaint import Complaint


SUGGESTION_URLS = (
    "/api/v1/departments/suggest",
    "/api/v1/complaints/suggest",  # Keep the Sprint 1 compatibility alias
)


@pytest.mark.parametrize("endpoint", SUGGESTION_URLS)
@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("title", "  x  "),         # Raw length 5, meaningful length 1
        ("description", "       x       "),  # Raw length 15, meaningful length 1
        ("title", "    "),
        ("description", "            "),
    ],
)
def test_suggestion_rejects_too_short_after_trimming(
    client, student_headers, endpoint, field, invalid_value
):
    payload = {
        "title": "Campus Wi-Fi unavailable",
        "description": "Wi-Fi and internet access have been unavailable today.",
    }
    payload[field] = invalid_value
    response = client.post(endpoint, json=payload, headers=student_headers)
    assert response.status_code == 422


@pytest.mark.parametrize("endpoint", SUGGESTION_URLS)
def test_valid_suggestion_accepts_padded_text_and_recommends_it(
    client, student_headers, seeded_departments, endpoint
):
    response = client.post(
        endpoint,
        json={
            "title": "   Campus Wi-Fi is broken   ",
            "description": "   Internet and network are unavailable in classrooms.   ",
        },
        headers=student_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "provisional_advisory"
    assert data["suggestions"][0]["department_name"] == "IT Services"


@pytest.mark.parametrize("endpoint", SUGGESTION_URLS)
def test_suggestion_rejects_injected_fields(client, student_headers, endpoint):
    response = client.post(
        endpoint,
        json={
            "title": "Campus network unavailable",
            "description": "Campus Wi-Fi disconnected during the lecture today.",
            "force_department_id": 1,
        },
        headers=student_headers,
    )
    assert response.status_code == 422


def test_complaint_rejects_client_supplied_creator_and_status(
    client, db, student_headers, seeded_departments
):
    initial_count = db.query(Complaint).count()
    payload = {
        "title": "Broken router in lab",
        "description": "The campus network router stopped working before class.",
        "department_id": seeded_departments["it"].id,
        "created_by_id": 999999,
        "status": "resolved",
    }
    response = client.post("/api/v1/complaints", json=payload, headers=student_headers)
    assert response.status_code == 422
    assert db.query(Complaint).count() == initial_count


def test_mine_large_offset_returns_empty_not_another_students_complaints(
    client, student_headers, student_b_headers, seeded_departments
):
    payload = {
        "title": "Private network issue",
        "description": "Connection stopped working during evening lab sessions.",
        "department_id": seeded_departments["it"].id,
    }
    response = client.post("/api/v1/complaints", json=payload, headers=student_b_headers)
    assert response.status_code == 201
    mine = client.get("/api/v1/complaints/mine?limit=1&offset=999", headers=student_headers)
    assert mine.status_code == 200
    assert mine.json() == []


@pytest.mark.parametrize("endpoint", SUGGESTION_URLS)
def test_suggestion_requires_authenticated_student(
    client, staff_headers, endpoint
):
    payload = {
        "title": "Network connection down",
        "description": "The campus Wi-Fi network has been offline all morning.",
    }
    assert client.post(endpoint, json=payload).status_code == 401
    assert client.post(endpoint, json=payload, headers=staff_headers).status_code == 403
