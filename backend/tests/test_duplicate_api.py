"""HTTP integration tests for duplicate suggestions."""

from app.models.complaint import Complaint


URL = "/api/v1/complaints/duplicate-suggestions"

DRAFT = {
    "title": "Campus wifi router broken",
    "description": "The campus wifi router is broken and internet is unavailable.",
}


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


def test_duplicate_endpoint_validates_input(
    client, student_headers
):
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
    public = Complaint(
        title=DRAFT["title"],
        description=DRAFT["description"],
        department_id=seeded_departments["hostel"].id,
        created_by_id=student_b_user.id,
        status="submitted",
        is_public=True,
        visibility_scope="department_public",
        feed_review_status="not_required",
        publication_status="published",
    )
    db.add(public)
    db.commit()

    response = client.post(
        URL, json=DRAFT, headers=student_headers
    )

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
    other_private = Complaint(
        title=DRAFT["title"],
        description=DRAFT["description"],
        department_id=seeded_departments["hostel"].id,
        created_by_id=student_b_user.id,
        status="submitted",
        is_public=False,
    )
    db.add(other_private)
    db.commit()

    response = client.post(
        URL, json=DRAFT, headers=student_headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["matches"] == []


def test_duplicate_endpoint_includes_own_private_complaint(
    client, db, seeded_departments,
    student_user, student_headers
):
    own_private = Complaint(
        title=DRAFT["title"],
        description=DRAFT["description"],
        department_id=seeded_departments["hostel"].id,
        created_by_id=student_user.id,
        status="submitted",
        is_public=False,
    )
    db.add(own_private)
    db.commit()

    response = client.post(
        URL, json=DRAFT, headers=student_headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["matches"][0]["id"] == own_private.id
