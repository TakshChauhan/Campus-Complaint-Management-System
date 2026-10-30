"""Sprint 3 canonical location tree and residence verification (API contract 7.2-7.5)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.student_residence import StudentResidence
from sprint3_hmc_world import build_world, headers_for, make_user, set_residence

LOCATIONS = "/api/v1/locations/hostels"
MY_RESIDENCE = "/api/v1/users/me/residence"
QUEUE = "/api/v1/staff/residences"


def decide(residence_id):
    return f"{QUEUE}/{residence_id}/decision"


@pytest.fixture
def world(db, seeded_departments, student_user, student_b_user):
    return build_world(db, seeded_departments, student_user, student_b_user)


@pytest.fixture
def newcomer(db):
    return make_user(db, "newcomer", "student")


# --- Location tree -------------------------------------------------------------------

def test_location_tree_lists_only_active_entries_for_any_role(
    client, db, world, student_headers, staff_headers, admin_headers,
):
    world["floors"]["A3"].is_active = False
    world["wings"]["D"].is_active = False
    world["new"].is_active = False
    db.commit()
    assert client.get(LOCATIONS).status_code == 401
    for headers in (student_headers, staff_headers, admin_headers):
        response = client.get(LOCATIONS, headers=headers)
        assert response.status_code == 200
        tree = response.json()
        assert [h["code"] for h in tree] == ["MH"]
        wings = {w["code"]: [f["code"] for f in w["floors"]] for w in tree[0]["wings"]}
        assert wings == {"A": ["1", "2"], "B": ["1", "2", "3"], "C": ["1", "2", "3"]}
        assert set(tree[0]) == {"id", "code", "name", "wings"}
        assert set(tree[0]["wings"][0]["floors"][0]) == {"id", "code", "name"}


def test_location_tree_reveals_no_hmc_or_residence_data(client, world, student_headers):
    serialized = client.get(LOCATIONS, headers=student_headers).text
    assert "HMC" not in serialized and "@" not in serialized


# --- Student residence ---------------------------------------------------------------

def test_student_without_residence_gets_404_and_other_roles_get_403(
    client, world, newcomer, staff_headers, admin_headers,
):
    assert client.get(MY_RESIDENCE, headers=headers_for(newcomer)).status_code == 404
    for headers in (staff_headers, admin_headers):
        assert client.get(MY_RESIDENCE, headers=headers).status_code == 403
        assert client.patch(MY_RESIDENCE, headers=headers, json={"floor_id": world["floors"]["A1"].id}).status_code == 403
    assert client.get(MY_RESIDENCE).status_code == 401


def test_student_sets_a_pending_residence(client, world, newcomer):
    floor = world["floors"]["B2"]
    response = client.patch(MY_RESIDENCE, headers=headers_for(newcomer), json={"floor_id": floor.id})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "floor_id": floor.id, "hostel": "Main Hostel", "wing": "Wing B", "floor": "Floor 2",
        "status": "pending", "remark": None,
    }
    assert client.get(MY_RESIDENCE, headers=headers_for(newcomer)).json()["status"] == "pending"


@pytest.mark.parametrize("body", [
    {"floor_id": 0}, {"floor_id": -1}, {"floor_id": "abc"}, {},
    {"floor_id": 1, "status": "verified"}, {"floor_id": 1, "hmc_group_id": 1},
])
def test_residence_update_rejects_invalid_bodies(client, world, newcomer, body):
    assert client.patch(MY_RESIDENCE, headers=headers_for(newcomer), json=body).status_code == 422


@pytest.mark.parametrize("deactivate", ["floor", "wing", "hostel", "unknown"])
def test_residence_update_rejects_unknown_or_inactive_locations(client, db, world, newcomer, deactivate):
    floor = world["floors"]["C2"]
    floor_id = floor.id
    if deactivate == "floor":
        floor.is_active = False
    elif deactivate == "wing":
        world["wings"]["C"].is_active = False
    elif deactivate == "hostel":
        world["main"].is_active = False
    else:
        floor_id = 999999
    db.commit()
    assert client.patch(MY_RESIDENCE, headers=headers_for(newcomer), json={"floor_id": floor_id}).status_code == 422


def test_changing_a_verified_or_rejected_residence_requires_reverification(
    client, db, world, student_user, student_headers,
):
    residence = db.query(StudentResidence).filter_by(student_id=student_user.id).one()
    residence.remark = "Old remark"
    db.commit()
    for status in ("verified", "rejected"):
        set_residence(db, student_user, world["floors"]["A1"], world["hostel_staff"], status=status)
        response = client.patch(MY_RESIDENCE, headers=student_headers, json={"floor_id": world["floors"]["A2"].id})
        assert response.status_code == 200
        assert response.json()["status"] == "pending" and response.json()["remark"] is None
        db.expire_all()
        stored = db.query(StudentResidence).filter_by(student_id=student_user.id).one()
        assert stored.verified_by_id is None and stored.verified_at is None
    assert db.query(StudentResidence).filter_by(student_id=student_user.id).count() == 1


# --- Hostel staff verification queue ---------------------------------------------------

def test_residence_queue_is_restricted_to_hostel_staff_and_admins(
    client, world, student_headers, staff_headers, admin_headers,
):
    assert client.get(QUEUE, headers=admin_headers).status_code == 200
    assert client.get(QUEUE, headers=headers_for(world["hostel_staff"])).status_code == 200
    for headers in (student_headers, staff_headers, headers_for(world["it_staff"])):
        assert client.get(QUEUE, headers=headers).status_code == 403
    assert client.get(QUEUE).status_code == 401


def test_residence_queue_filters_orders_paginates_and_identifies_students(
    client, db, world, admin_headers,
):
    students = [make_user(db, f"queue{i}", "student") for i in range(3)]
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for offset, student in zip((2, 0, 1), students):
        db.add(StudentResidence(student_id=student.id, floor_id=world["floors"]["A2"].id,
                                submitted_at=base + timedelta(hours=offset)))
    db.commit()
    page = client.get(f"{QUEUE}?limit=2", headers=admin_headers)
    assert page.status_code == 200
    assert page.headers["X-Total-Count"] == "3"
    assert [item["student_id"] for item in page.json()] == [students[1].id, students[2].id]
    rest = client.get(f"{QUEUE}?limit=2&offset=2", headers=admin_headers).json()
    assert [item["student_email"] for item in rest] == [students[0].email]
    assert set(rest[0]) == {
        "id", "student_id", "student_name", "student_email", "floor_id", "hostel", "wing", "floor",
        "status", "remark", "submitted_at", "decided_at",
    }
    verified = client.get(f"{QUEUE}?status=verified", headers=admin_headers)
    assert verified.headers["X-Total-Count"] == "2"  # Alice and Bob from the world fixture
    assert client.get(f"{QUEUE}?status=approved", headers=admin_headers).status_code == 422
    assert client.get(f"{QUEUE}?limit=101", headers=admin_headers).status_code == 422


def test_hostel_staff_approve_a_residence_and_grant_hmc_membership(client, db, world, newcomer):
    new_headers = headers_for(newcomer)
    client.patch(MY_RESIDENCE, headers=new_headers, json={"floor_id": world["floors"]["B1"].id})
    assert client.get("/api/v1/feeds/hostel", headers=new_headers).status_code == 403
    residence_id = db.query(StudentResidence).filter_by(student_id=newcomer.id).one().id

    response = client.post(decide(residence_id), headers=headers_for(world["hostel_staff"]), json={"decision": "approve"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "verified" and data["decided_at"] is not None
    assert data["student_email"] == newcomer.email
    assert client.get(MY_RESIDENCE, headers=new_headers).json()["status"] == "verified"
    assert client.get("/api/v1/feeds/hostel", headers=new_headers).status_code == 200
    # Already decided.
    assert client.post(decide(residence_id), headers=headers_for(world["hostel_staff"]),
                       json={"decision": "reject", "remark": "Changed mind."}).status_code == 409


def test_rejection_requires_a_remark_and_shows_it_to_the_student(client, db, world, newcomer, admin_headers):
    client.patch(MY_RESIDENCE, headers=headers_for(newcomer), json={"floor_id": world["floors"]["C1"].id})
    residence_id = db.query(StudentResidence).filter_by(student_id=newcomer.id).one().id
    for body in ({"decision": "reject"}, {"decision": "reject", "remark": "   "},
                 {"decision": "maybe"}, {"decision": "approve", "status": "verified"},
                 {"decision": "reject", "remark": "x" * 2001}):
        assert client.post(decide(residence_id), headers=admin_headers, json=body).status_code == 422
    response = client.post(decide(residence_id), headers=admin_headers,
                           json={"decision": "reject", "remark": "Room allotment list shows a different floor."})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    mine = client.get(MY_RESIDENCE, headers=headers_for(newcomer)).json()
    assert mine["status"] == "rejected" and mine["remark"] == "Room allotment list shows a different floor."
    assert client.get("/api/v1/feeds/hostel", headers=headers_for(newcomer)).status_code == 403


def test_decision_permissions_and_unknown_ids(client, db, world, newcomer, student_headers, staff_headers):
    client.patch(MY_RESIDENCE, headers=headers_for(newcomer), json={"floor_id": world["floors"]["C1"].id})
    residence_id = db.query(StudentResidence).filter_by(student_id=newcomer.id).one().id
    for headers in (student_headers, headers_for(newcomer), staff_headers, headers_for(world["it_staff"])):
        assert client.post(decide(residence_id), headers=headers, json={"decision": "approve"}).status_code == 403
    assert client.post(decide(999999), headers=headers_for(world["hostel_staff"]), json={"decision": "approve"}).status_code == 404
    assert client.post(decide(0), headers=headers_for(world["hostel_staff"]), json={"decision": "approve"}).status_code == 422
    assert db.query(StudentResidence).filter_by(student_id=newcomer.id).one().status == "pending"


def test_hostel_staff_lose_review_rights_when_the_hostel_department_is_inactive(
    client, db, world, seeded_departments,
):
    seeded_departments["hostel"].is_active = False
    db.commit()
    assert client.get(QUEUE, headers=headers_for(world["hostel_staff"])).status_code == 403
