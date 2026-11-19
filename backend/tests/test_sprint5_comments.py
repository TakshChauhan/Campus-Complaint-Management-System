"""S5-05: complaint comments (User Story 6, API contract 7.16).

Owner routes:  GET/POST /api/v1/complaints/{id}/comments
Staff routes:  GET/POST /api/v1/staff/complaints/{id}/comments

Access follows the complaint detail routes: the student owner, or staff of the
handling department (and, for Hostel staff, an assigned hostel). Everybody
else who is signed in gets 404; no token gets 401.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.complaint import Complaint
from app.models.complaint_comment import ComplaintComment
from app.models.department import Department
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.staff_hostel_assignment import StaffHostelAssignment
from app.models.user import User

API = "/api/v1"


def _headers(user: User) -> dict:
    token = create_access_token(subject=str(user.id), claims={"role": user.role, "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def owner_url(complaint_id: int) -> str:
    return f"{API}/complaints/{complaint_id}/comments"


def staff_url(complaint_id: int) -> str:
    return f"{API}/staff/complaints/{complaint_id}/comments"


@pytest.fixture
def world(db: Session, seeded_departments: dict) -> dict:
    hostel_dept = seeded_departments["hostel"]
    it_dept = seeded_departments["it"]
    library_dept = seeded_departments["library"]

    hostel_a = Hostel(code="C5A", name="Comments Hostel A", is_active=True)
    hostel_b = Hostel(code="C5B", name="Comments Hostel B", is_active=True)
    db.add_all([hostel_a, hostel_b])
    db.flush()
    wing_a = HostelWing(hostel_id=hostel_a.id, code="WA", name="Wing A", is_active=True)
    wing_b = HostelWing(hostel_id=hostel_b.id, code="WB", name="Wing B", is_active=True)
    db.add_all([wing_a, wing_b])
    db.flush()
    floor_a = HostelFloor(wing_id=wing_a.id, code="F1", name="Floor 1", is_active=True)
    floor_b = HostelFloor(wing_id=wing_b.id, code="F1", name="Floor 1", is_active=True)
    db.add_all([floor_a, floor_b])
    db.flush()

    users = {
        "owner": User(name="Owner Student", email="owner.s5@student.campus.edu", role="student"),
        "other_student": User(name="Other Student", email="other.s5@student.campus.edu", role="student"),
        "it_staff": User(name="IT Staff", email="it.s5@campus.edu", role="staff", department_id=it_dept.id),
        "library_staff": User(
            name="Library Staff", email="lib.s5@campus.edu", role="staff", department_id=library_dept.id
        ),
        "hostel_a_staff": User(
            name="Warden A", email="warden.a.s5@campus.edu", role="staff", department_id=hostel_dept.id
        ),
        "hostel_b_staff": User(
            name="Warden B", email="warden.b.s5@campus.edu", role="staff", department_id=hostel_dept.id
        ),
        "hostel_no_hostels": User(
            name="Warden None", email="warden.none.s5@campus.edu", role="staff", department_id=hostel_dept.id
        ),
        "no_dept_staff": User(name="Floating Staff", email="float.s5@campus.edu", role="staff"),
        "admin": User(name="Admin S5", email="admin.s5@campus.edu", role="admin"),
    }
    for user in users.values():
        user.is_active = True
    db.add_all(users.values())
    db.flush()

    db.add_all(
        [
            StaffHostelAssignment(
                user_id=users["hostel_a_staff"].id, hostel_id=hostel_a.id, assigned_by_id=users["admin"].id
            ),
            StaffHostelAssignment(
                user_id=users["hostel_b_staff"].id, hostel_id=hostel_b.id, assigned_by_id=users["admin"].id
            ),
        ]
    )

    it_complaint = Complaint(
        title="Wi-Fi down in library",
        description="No connectivity since morning",
        department_id=it_dept.id,
        created_by_id=users["owner"].id,
        status="submitted",
    )
    hostel_complaint = Complaint(
        title="Tap leaking",
        description="Bathroom tap on floor 1 leaks",
        department_id=hostel_dept.id,
        created_by_id=users["owner"].id,
        floor_id=floor_a.id,
        status="in_progress",
    )
    db.add_all([it_complaint, hostel_complaint])
    db.commit()

    return {"users": users, "it": it_complaint, "hostel": hostel_complaint}


def _add(db: Session, complaint: Complaint, author: User, body: str, created_at: datetime) -> ComplaintComment:
    comment = ComplaintComment(complaint_id=complaint.id, author_id=author.id, body=body, created_at=created_at)
    db.add(comment)
    db.commit()
    return comment


# --- Owner -----------------------------------------------------------------


def test_owner_posts_and_reads_comment(client: TestClient, world: dict):
    owner = world["users"]["owner"]
    complaint = world["it"]

    created = client.post(owner_url(complaint.id), json={"body": "  Any update?  "}, headers=_headers(owner))
    assert created.status_code == 201, created.text
    data = created.json()
    assert set(data) == {"id", "body", "created_at", "author_role", "author_name", "is_mine"}
    assert data["body"] == "Any update?"
    assert data["author_role"] == "student"
    assert data["author_name"] == "Owner Student"
    assert data["is_mine"] is True

    listed = client.get(owner_url(complaint.id), headers=_headers(owner))
    assert listed.status_code == 200
    assert listed.headers["X-Total-Count"] == "1"
    assert [c["id"] for c in listed.json()] == [data["id"]]


def test_owner_sees_staff_reply_as_not_mine(client: TestClient, world: dict):
    owner = world["users"]["owner"]
    staff = world["users"]["it_staff"]
    complaint = world["it"]

    client.post(owner_url(complaint.id), json={"body": "Still broken"}, headers=_headers(owner))
    client.post(staff_url(complaint.id), json={"body": "Technician assigned"}, headers=_headers(staff))

    owner_view = client.get(owner_url(complaint.id), headers=_headers(owner)).json()
    assert [(c["author_role"], c["is_mine"]) for c in owner_view] == [("student", True), ("staff", False)]

    staff_view = client.get(staff_url(complaint.id), headers=_headers(staff)).json()
    assert [(c["author_role"], c["is_mine"]) for c in staff_view] == [("student", False), ("staff", True)]
    assert staff_view[1]["author_name"] == "IT Staff"


# --- Staff in scope --------------------------------------------------------


def test_department_staff_reads_and_posts(client: TestClient, world: dict):
    staff = world["users"]["it_staff"]
    complaint = world["it"]

    created = client.post(staff_url(complaint.id), json={"body": "Looking into it"}, headers=_headers(staff))
    assert created.status_code == 201, created.text
    assert created.json()["author_role"] == "staff"

    listed = client.get(staff_url(complaint.id), headers=_headers(staff))
    assert listed.status_code == 200
    assert listed.headers["X-Total-Count"] == "1"


def test_hostel_staff_in_assigned_hostel_reads_and_posts(client: TestClient, world: dict):
    warden = world["users"]["hostel_a_staff"]
    complaint = world["hostel"]

    created = client.post(staff_url(complaint.id), json={"body": "Plumber visiting today"}, headers=_headers(warden))
    assert created.status_code == 201, created.text
    assert client.get(staff_url(complaint.id), headers=_headers(warden)).status_code == 200


# --- Out of scope: always 404 ----------------------------------------------


@pytest.mark.parametrize("method", ["get", "post"])
def test_other_student_gets_404(client: TestClient, world: dict, method: str):
    other = world["users"]["other_student"]
    kwargs = {"headers": _headers(other)}
    if method == "post":
        kwargs["json"] = {"body": "Not mine"}
    response = getattr(client, method)(owner_url(world["it"].id), **kwargs)
    assert response.status_code == 404
    assert response.json() == {"detail": "Complaint not found."}


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize(
    ("user_key", "complaint_key"),
    [
        ("library_staff", "it"),  # other department
        ("it_staff", "hostel"),  # other department (hostel complaint)
        ("hostel_b_staff", "hostel"),  # Hostel staff outside their hostel
        ("hostel_no_hostels", "hostel"),  # Hostel staff with no hostels
        ("no_dept_staff", "it"),  # staff with no department
    ],
)
def test_out_of_scope_staff_get_404(client: TestClient, world: dict, method, user_key, complaint_key):
    user = world["users"][user_key]
    kwargs = {"headers": _headers(user)}
    if method == "post":
        kwargs["json"] = {"body": "Should not land"}
    response = getattr(client, method)(staff_url(world[complaint_key].id), **kwargs)
    assert response.status_code == 404
    assert response.json() == {"detail": "Complaint not found."}


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize(
    ("user_key", "url_kind"),
    [
        ("owner", "staff"),  # the owner on the staff route
        ("other_student", "staff"),
        ("it_staff", "owner"),  # in-scope staff on the owner route
        ("admin", "owner"),  # admin access is not in v1
        ("admin", "staff"),
    ],
)
def test_wrong_route_family_gets_404(client: TestClient, world: dict, method, user_key, url_kind):
    user = world["users"][user_key]
    url = (owner_url if url_kind == "owner" else staff_url)(world["it"].id)
    kwargs = {"headers": _headers(user)}
    if method == "post":
        kwargs["json"] = {"body": "Should not land"}
    assert getattr(client, method)(url, **kwargs).status_code == 404


def test_staff_of_inactive_department_get_404(client: TestClient, db: Session, world: dict):
    staff = world["users"]["it_staff"]
    db.query(Department).filter(Department.id == staff.department_id).update({"is_active": False})
    db.commit()
    assert client.get(staff_url(world["it"].id), headers=_headers(staff)).status_code == 404
    assert client.post(staff_url(world["it"].id), json={"body": "x"}, headers=_headers(staff)).status_code == 404


def test_legacy_hostel_text_follows_the_detail_route(
    client: TestClient, db: Session, world: dict, seeded_departments: dict
):
    """A text-only (no floor_id) complaint naming Hostel B: same answer as the detail route (#95)."""
    legacy = Complaint(
        title="Legacy location",
        description="Only hostel text recorded",
        department_id=seeded_departments["hostel"].id,
        created_by_id=world["users"]["owner"].id,
        floor_id=None,
        hostel="Comments Hostel B",
        status="submitted",
    )
    db.add(legacy)
    db.commit()
    for key, expected in (("hostel_a_staff", 404), ("hostel_b_staff", 200)):
        headers = _headers(world["users"][key])
        assert client.get(f"{API}/staff/complaints/{legacy.id}", headers=headers).status_code == expected
        assert client.get(staff_url(legacy.id), headers=headers).status_code == expected


def test_deactivated_account_gets_403(client: TestClient, db: Session, world: dict):
    owner = world["users"]["owner"]
    owner.is_active = False
    db.commit()
    assert client.get(owner_url(world["it"].id), headers=_headers(owner)).status_code == 403


def test_missing_complaint_gives_404(client: TestClient, world: dict):
    owner = world["users"]["owner"]
    staff = world["users"]["it_staff"]
    assert client.get(owner_url(999_999), headers=_headers(owner)).status_code == 404
    assert client.get(staff_url(999_999), headers=_headers(staff)).status_code == 404


@pytest.mark.parametrize("url_fn", [owner_url, staff_url])
def test_unauthenticated_gets_401(client: TestClient, world: dict, url_fn):
    assert client.get(url_fn(world["it"].id)).status_code == 401
    assert client.post(url_fn(world["it"].id), json={"body": "hi"}).status_code == 401


def test_denied_posts_write_nothing(client: TestClient, db: Session, world: dict):
    complaint = world["hostel"]
    client.post(owner_url(complaint.id), json={"body": "x"}, headers=_headers(world["users"]["other_student"]))
    client.post(staff_url(complaint.id), json={"body": "x"}, headers=_headers(world["users"]["hostel_b_staff"]))
    assert db.query(ComplaintComment).filter_by(complaint_id=complaint.id).count() == 0


# --- Validation ------------------------------------------------------------


@pytest.mark.parametrize("body", ["", "   ", "\n\t "])
@pytest.mark.parametrize("url_kind", ["owner", "staff"])
def test_blank_body_is_422(client: TestClient, world: dict, body: str, url_kind: str):
    if url_kind == "owner":
        url, user = owner_url(world["it"].id), world["users"]["owner"]
    else:
        url, user = staff_url(world["it"].id), world["users"]["it_staff"]
    assert client.post(url, json={"body": body}, headers=_headers(user)).status_code == 422


@pytest.mark.parametrize("url_kind", ["owner", "staff"])
def test_body_over_1000_characters_is_422(client: TestClient, world: dict, url_kind: str):
    if url_kind == "owner":
        url, user = owner_url(world["it"].id), world["users"]["owner"]
    else:
        url, user = staff_url(world["it"].id), world["users"]["it_staff"]
    assert client.post(url, json={"body": "a" * 1001}, headers=_headers(user)).status_code == 422


def test_body_boundaries_1_and_1000_accepted_after_strip(client: TestClient, world: dict):
    owner = world["users"]["owner"]
    url = owner_url(world["it"].id)
    one = client.post(url, json={"body": " a "}, headers=_headers(owner))
    assert one.status_code == 201 and one.json()["body"] == "a"
    # 1000 characters of content plus surrounding whitespace is still valid.
    full = client.post(url, json={"body": "  " + "b" * 1000 + "  "}, headers=_headers(owner))
    assert full.status_code == 201 and len(full.json()["body"]) == 1000


@pytest.mark.parametrize("payload", [{}, {"body": None}, {"body": 5}, {"body": "ok", "author_id": 1}])
def test_malformed_payload_is_422(client: TestClient, world: dict, payload: dict):
    response = client.post(owner_url(world["it"].id), json=payload, headers=_headers(world["users"]["owner"]))
    assert response.status_code == 422


def test_database_rejects_empty_body(db: Session, world: dict):
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(ComplaintComment(complaint_id=world["it"].id, author_id=world["users"]["owner"].id, body=""))
            db.flush()


# --- Ordering and pagination ----------------------------------------------


def test_comments_oldest_first_with_id_tiebreak(client: TestClient, db: Session, world: dict):
    owner = world["users"]["owner"]
    staff = world["users"]["it_staff"]
    complaint = world["it"]
    base = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)
    third = _add(db, complaint, owner, "third", base + timedelta(minutes=5))
    first = _add(db, complaint, staff, "first", base)
    second = _add(db, complaint, owner, "second", base)  # same time as "first", higher id

    bodies = [c["body"] for c in client.get(owner_url(complaint.id), headers=_headers(owner)).json()]
    # Insertion order (ids) differs from the expected order, so this proves the
    # sort is by created_at first and id only breaks ties.
    assert third.id < first.id < second.id
    assert bodies == ["first", "second", "third"]


def test_limit_offset_and_total_count(client: TestClient, db: Session, world: dict):
    owner = world["users"]["owner"]
    complaint = world["it"]
    base = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)
    for i in range(5):
        _add(db, complaint, owner, f"c{i}", base + timedelta(minutes=i))

    page = client.get(owner_url(complaint.id), params={"limit": 2, "offset": 1}, headers=_headers(owner))
    assert page.status_code == 200
    assert page.headers["X-Total-Count"] == "5"
    assert [c["body"] for c in page.json()] == ["c1", "c2"]

    tail = client.get(owner_url(complaint.id), params={"limit": 2, "offset": 4}, headers=_headers(owner))
    assert [c["body"] for c in tail.json()] == ["c4"]
    assert tail.headers["X-Total-Count"] == "5"


def test_default_limit_is_50(client: TestClient, db: Session, world: dict):
    owner = world["users"]["owner"]
    complaint = world["it"]
    base = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)
    db.add_all(
        ComplaintComment(complaint_id=complaint.id, author_id=owner.id, body=f"c{i}", created_at=base + timedelta(seconds=i))
        for i in range(55)
    )
    db.commit()
    response = client.get(owner_url(complaint.id), headers=_headers(owner))
    assert len(response.json()) == 50
    assert response.headers["X-Total-Count"] == "55"


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_pagination_bounds_are_422(client: TestClient, world: dict, params: dict):
    response = client.get(owner_url(world["it"].id), params=params, headers=_headers(world["users"]["owner"]))
    assert response.status_code == 422


def test_empty_list(client: TestClient, world: dict):
    response = client.get(owner_url(world["it"].id), headers=_headers(world["users"]["owner"]))
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["X-Total-Count"] == "0"


# --- Privacy and lifecycle -------------------------------------------------


def test_response_never_contains_email_or_user_id(client: TestClient, world: dict):
    owner = world["users"]["owner"]
    staff = world["users"]["it_staff"]
    complaint = world["it"]
    client.post(owner_url(complaint.id), json={"body": "hello"}, headers=_headers(owner))
    client.post(staff_url(complaint.id), json={"body": "hi"}, headers=_headers(staff))

    for url, user in ((owner_url(complaint.id), owner), (staff_url(complaint.id), staff)):
        response = client.get(url, headers=_headers(user))
        raw = response.text
        assert owner.email not in raw and staff.email not in raw
        for item in response.json():
            assert "author_id" not in item and "email" not in item and "user_id" not in item
            assert "complaint_id" not in item


@pytest.mark.parametrize("status_value", ["submitted", "in_progress", "resolved", "reopened", "rejected"])
def test_comments_open_in_every_status(client: TestClient, db: Session, world: dict, status_value: str):
    complaint = world["it"]
    # Set directly: this test is about comments, not the lifecycle rules.
    db.query(Complaint).filter(Complaint.id == complaint.id).update({"status": status_value})
    db.commit()
    owner = world["users"]["owner"]
    staff = world["users"]["it_staff"]
    assert client.post(owner_url(complaint.id), json={"body": "Why?"}, headers=_headers(owner)).status_code == 201
    assert client.post(staff_url(complaint.id), json={"body": "Because"}, headers=_headers(staff)).status_code == 201


def test_comments_are_append_only(client: TestClient, world: dict):
    owner = world["users"]["owner"]
    complaint = world["it"]
    created = client.post(owner_url(complaint.id), json={"body": "original"}, headers=_headers(owner)).json()
    item_url = f"{owner_url(complaint.id)}/{created['id']}"
    assert client.patch(item_url, json={"body": "edited"}, headers=_headers(owner)).status_code == 404
    assert client.delete(item_url, headers=_headers(owner)).status_code == 404
    assert client.delete(owner_url(complaint.id), headers=_headers(owner)).status_code == 405
    assert [c["body"] for c in client.get(owner_url(complaint.id), headers=_headers(owner)).json()] == ["original"]


def test_comments_do_not_leak_into_complaint_detail(client: TestClient, world: dict):
    owner = world["users"]["owner"]
    staff = world["users"]["it_staff"]
    complaint = world["it"]
    client.post(owner_url(complaint.id), json={"body": "secret-marker-123"}, headers=_headers(owner))

    student_detail = client.get(f"{API}/complaints/{complaint.id}", headers=_headers(owner))
    staff_detail = client.get(f"{API}/staff/complaints/{complaint.id}", headers=_headers(staff))
    for response in (student_detail, staff_detail):
        assert response.status_code == 200
        assert "secret-marker-123" not in response.text
        assert "comments" not in response.json()


def test_comments_do_not_leak_into_complaint_lists(client: TestClient, world: dict):
    owner = world["users"]["owner"]
    staff = world["users"]["it_staff"]
    complaint = world["it"]
    client.post(owner_url(complaint.id), json={"body": "list-marker-456"}, headers=_headers(owner))

    my_list = client.get(f"{API}/complaints/mine", headers=_headers(owner))
    staff_queue = client.get(f"{API}/staff/complaints", headers=_headers(staff))
    for response in (my_list, staff_queue):
        assert response.status_code == 200
        assert "list-marker-456" not in response.text
        items = response.json()
        items = items["items"] if isinstance(items, dict) else items
        assert any(item["id"] == complaint.id for item in items)
        assert all("comments" not in item for item in items)
