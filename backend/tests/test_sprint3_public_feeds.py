"""Public feeds, Model 2 hostel visibility, moderation and duplicate-candidate security.

Ported from PR #46 to the canonical hostel hierarchy in Sprint 3 and updated
for Model 2 in Sprint 4 (S4-09): a verified resident sees their own hostel,
Hostel-department staff and admins moderate, and HMC groups no longer decide
visibility. Alice lives on Main Hostel A1, Bob on Main Hostel C1, and the
``nh_resident`` fixture on New Hostel N1.
"""
import pytest

from app.core.config import settings
from app.models.complaint import Complaint
from app.models.complaint_hmc_audience import ComplaintHMCAudience
from app.models.complaint_publication_audit import ComplaintPublicationAudit
from app.models.hmc_group import HMCGroupFloor
from sprint3_hmc_world import (
    FORBIDDEN_FEED_KEYS, FEED_ITEM_KEYS, HOSTEL_FEED_ITEM_KEYS, build_world, duplicate_ids,
    feed_ids, headers_for, make_user, set_residence, submit,
)

HOSTEL_FEED = "/api/v1/feeds/hostel"
QUEUE = "/api/v1/hmc/publication-requests"


def dept_feed(department_id):
    return f"/api/v1/feeds/departments/{department_id}"


def decision(complaint_id):
    return f"/api/v1/hmc/publication-requests/{complaint_id}/decision"


@pytest.fixture
def world(db, seeded_departments, student_user, student_b_user):
    return build_world(db, seeded_departments, student_user, student_b_user)


@pytest.fixture
def nh_resident(db, world):
    """A verified resident of the New Hostel: an outsider for every Main Hostel complaint."""
    user = make_user(db, "nh.resident", "student")
    set_residence(db, user, world["floors"]["N1"], world["hostel_staff"])
    return user


@pytest.fixture
def nh_headers(nh_resident):
    return headers_for(nh_resident)


# --- Department feed -----------------------------------------------------------

def test_department_feed_excludes_hostel_scoped_and_never_returns_description_or_reporter_identity(
    client, world, student_headers, seeded_departments,
):
    dep = seeded_departments["it"].id
    department_public = submit(client, student_headers, dep, "Campus Wi-Fi outage")
    located = submit(client, student_headers, dep, "Wing C access point broken", floor_id=world["floors"]["C1"].id)
    assert department_public.status_code == 201, department_public.text
    assert department_public.json()["publication_status"] == "published"
    assert located.status_code == 201, located.text
    # Alice's own hostel, so it is published, but to the hostel feed only.
    assert located.json()["publication_status"] == "published"

    response = client.get(dept_feed(dep), headers=student_headers)
    assert response.headers["X-Total-Count"] == "1"
    assert feed_ids(response) == {department_public.json()["id"]}
    item = response.json()[0]
    assert set(item) == FEED_ITEM_KEYS
    assert item["title"] == "Campus Wi-Fi outage"


def test_hostel_department_feed_is_rejected_for_every_authenticated_role(
    client, seeded_departments, student_headers, staff_headers, admin_headers,
):
    hostel_id = seeded_departments["hostel"].id
    for headers in (student_headers, staff_headers, admin_headers):
        response = client.get(dept_feed(hostel_id), headers=headers)
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "hostel_feed_required"


def test_department_feed_is_accessible_to_students_staff_and_admins(
    client, seeded_departments, student_headers, staff_headers, admin_headers,
):
    department_id = seeded_departments["it"].id
    created = submit(client, student_headers, department_id, "Campus public Wi-Fi issue")
    assert created.status_code == 201, created.text
    for headers in (student_headers, staff_headers, admin_headers):
        response = client.get(dept_feed(department_id), headers=headers)
        assert response.headers["X-Total-Count"] == "1"
        assert feed_ids(response) == {created.json()["id"]}


def test_department_feed_requires_auth_and_rejects_unknown_or_inactive_departments(
    client, seeded_departments, student_headers,
):
    assert client.get(dept_feed(seeded_departments["it"].id)).status_code == 401
    assert client.get(dept_feed(999999), headers=student_headers).status_code == 404
    assert client.get(dept_feed(seeded_departments["inactive"].id), headers=student_headers).status_code == 404
    assert client.get(dept_feed(0), headers=student_headers).status_code == 422
    assert client.get(dept_feed(seeded_departments["it"].id) + "?status=closed", headers=student_headers).status_code == 422


def test_department_feed_status_filter_and_pagination(client, seeded_departments, student_headers):
    dep = seeded_departments["library"].id
    ids = [submit(client, student_headers, dep, f"Library issue {i}").json()["id"] for i in range(3)]
    page = client.get(dept_feed(dep) + "?limit=2&offset=0", headers=student_headers)
    assert page.headers["X-Total-Count"] == "3"
    assert [item["id"] for item in page.json()] == [ids[2], ids[1]]
    rest = client.get(dept_feed(dep) + "?limit=2&offset=2", headers=student_headers)
    assert [item["id"] for item in rest.json()] == [ids[0]]
    assert client.get(dept_feed(dep) + "?status=resolved", headers=student_headers).json() == []


# --- Classification ---------------------------------------------------------------

def test_unlocated_public_hostel_complaint_never_leaks_via_detail_or_duplicates(
    client, db, world, seeded_departments, student_headers, student_b_headers, monkeypatch,
):
    # Legacy data: only possible while an operator has turned the floor requirement off.
    monkeypatch.setattr(settings, "HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID", False)
    created = submit(client, student_headers, seeded_departments["hostel"].id, "Unlocated hostel Wi-Fi outage")
    assert created.status_code == 201, created.text
    assert created.json()["publication_status"] == "pending_mapping"
    complaint_id = created.json()["id"]
    assert client.get(f"/api/v1/feeds/items/{complaint_id}", headers=student_b_headers).status_code == 404

    # Also protect against old/misclassified records that have no location.
    complaint = db.get(Complaint, complaint_id)
    complaint.visibility_scope = "department_public"
    complaint.feed_review_status = "not_required"
    complaint.publication_status = "published"
    db.commit()
    assert client.get(f"/api/v1/feeds/items/{complaint_id}", headers=student_b_headers).status_code == 404
    assert complaint_id not in duplicate_ids(
        client, student_b_headers, "Unlocated hostel Wi-Fi outage",
        "A detailed report describing the observed campus issue.",
    )


def test_unverified_residence_cannot_auto_publish_even_when_reporting_own_floor(
    client, db, world, student_user, student_headers, seeded_departments,
):
    set_residence(db, student_user, world["floors"]["A1"], None, status="pending")
    complaint = submit(client, student_headers, seeded_departments["hostel"].id,
                       "Unverified Wing A water issue", floor_id=world["floors"]["A1"].id)
    assert complaint.status_code == 201
    assert complaint.json()["publication_status"] == "pending_review"
    assert complaint.json()["feed_review_status"] == "pending"


def test_verified_resident_auto_publishes_reports_about_their_own_hostel(
    client, db, world, student_headers, student_b_headers, seeded_departments,
):
    response = submit(client, student_headers, seeded_departments["hostel"].id,
                      "Wing A light issue", floor_id=world["floors"]["A1"].id)
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["publication_status"] == "published"
    assert item["feed_review_status"] == "auto_approved"
    assert item["location"] == {"hostel": "Main Hostel", "wing": "Wing A", "floor": "Floor 1"}
    # Model 2 writes no HMC audience rows.
    assert db.query(ComplaintHMCAudience).filter_by(complaint_id=item["id"]).count() == 0
    assert item["id"] in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))
    assert item["id"] in feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers))  # same hostel, other wing


def test_reporting_another_wing_keeps_the_affected_location_and_another_hostel_needs_review(
    client, world, student_headers, seeded_departments,
):
    # Alice lives on A/1 (verified) but reports C/1: the location is C/1, not her residence.
    response = submit(client, student_headers, seeded_departments["hostel"].id,
                      "Wing C washroom leak", floor_id=world["floors"]["C1"].id)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["floor_id"] == world["floors"]["C1"].id
    assert data["location"] == {"hostel": "Main Hostel", "wing": "Wing C", "floor": "Floor 1"}
    assert data["publication_status"] == "published"  # still her own hostel
    other_hostel = submit(client, student_headers, seeded_departments["hostel"].id,
                          "New Hostel lift stuck", floor_id=world["floors"]["N1"].id)
    assert other_hostel.status_code == 201, other_hostel.text
    assert other_hostel.json()["location"] == {"hostel": "New Hostel", "wing": "Wing N", "floor": "Floor 1"}
    assert other_hostel.json()["publication_status"] == "pending_review"


def test_floor_without_an_hmc_group_publishes_because_groups_no_longer_decide_visibility(
    client, world, student_headers, student_b_headers, seeded_departments,
):
    response = submit(client, student_headers, seeded_departments["hostel"].id,
                      "Wing D floor 3 ventilation", floor_id=world["floors"]["D3"].id)
    assert response.status_code == 201, response.text
    assert response.json()["publication_status"] == "published"
    assert response.json()["feed_review_status"] == "auto_approved"
    for headers in (student_headers, student_b_headers):
        assert response.json()["id"] in feed_ids(client.get(HOSTEL_FEED, headers=headers))


def test_legacy_text_location_remains_pending_mapping_and_is_never_guessed(
    client, world, student_headers, seeded_departments,
):
    # "Main Hostel / A / 1" exactly matches canonical names, but text is never authorization.
    response = submit(client, student_headers, seeded_departments["it"].id,
                      "Legacy location complaint", hostel="Main Hostel", wing="Wing A", floor="Floor 1")
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["publication_status"] == "pending_mapping"
    assert data["floor_id"] is None and data["location"] is None
    assert data["hostel"] == "Main Hostel"
    assert data["id"] not in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))
    assert data["id"] not in feed_ids(client.get(dept_feed(seeded_departments["it"].id), headers=student_headers))


def test_private_location_complaint_never_enters_feeds(client, world, student_headers, seeded_departments):
    response = submit(client, student_headers, seeded_departments["it"].id, "Private Wing A concern",
                      is_public=False, floor_id=world["floors"]["A1"].id)
    assert response.status_code == 201
    data = response.json()
    assert data["publication_status"] == "private"
    assert data["visibility_scope"] == "private"
    assert data["id"] not in feed_ids(client.get(dept_feed(seeded_departments["it"].id), headers=student_headers))
    assert data["id"] not in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))


def test_hostel_complaints_require_a_floor_by_default(
    client, world, student_headers, seeded_departments, monkeypatch,
):
    assert settings.HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID is True
    missing = submit(client, student_headers, seeded_departments["hostel"].id, "Hostel fan broken")
    assert missing.status_code == 422
    assert missing.json()["detail"] == "floor_id is required for Hostel complaints."
    located = submit(client, student_headers, seeded_departments["hostel"].id, "Hostel fan broken",
                     floor_id=world["floors"]["A1"].id)
    assert located.status_code == 201
    # Other departments still accept unlocated complaints.
    assert submit(client, student_headers, seeded_departments["it"].id, "Campus Wi-Fi down").status_code == 201
    # An operator can still turn the requirement off; the complaint then waits for mapping.
    monkeypatch.setattr(settings, "HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID", False)
    unlocated = submit(client, student_headers, seeded_departments["hostel"].id, "Hostel fan broken")
    assert unlocated.status_code == 201 and unlocated.json()["publication_status"] == "pending_mapping"


def test_inactive_floor_is_rejected_on_submission(client, db, world, student_headers, seeded_departments):
    world["wings"]["D"].is_active = False
    db.commit()
    response = submit(client, student_headers, seeded_departments["hostel"].id, "Inactive wing",
                      floor_id=world["floors"]["D2"].id)
    assert response.status_code == 422


# --- Hostel feed: students -----------------------------------------------------------

def test_residents_share_their_hostel_feed_and_other_hostels_never_see_it(
    client, world, student_headers, student_b_headers, nh_headers, seeded_departments,
):
    hostel = seeded_departments["hostel"].id
    alice_item = submit(client, student_headers, hostel, "Wing A geyser broken",
                        floor_id=world["floors"]["A1"].id).json()
    bob_item = submit(client, student_b_headers, hostel, "Wing C geyser broken",
                      floor_id=world["floors"]["C1"].id).json()
    nh_item = submit(client, nh_headers, hostel, "Wing N geyser broken", floor_id=world["floors"]["N1"].id).json()
    assert alice_item["publication_status"] == bob_item["publication_status"] == nh_item["publication_status"] == "published"
    main = {alice_item["id"], bob_item["id"]}
    assert feed_ids(client.get(HOSTEL_FEED, headers=student_headers)) == main
    assert feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers)) == main
    assert feed_ids(client.get(HOSTEL_FEED, headers=nh_headers)) == {nh_item["id"]}
    # Guessing another hostel's detail ID returns 404, in both directions.
    assert client.get(f"/api/v1/feeds/items/{nh_item['id']}", headers=student_headers).status_code == 404
    assert client.get(f"/api/v1/feeds/items/{alice_item['id']}", headers=nh_headers).status_code == 404
    assert client.get(f"/api/v1/feeds/items/{bob_item['id']}", headers=student_headers).status_code == 200


def test_hostel_feed_items_follow_the_contract_shape(client, world, student_headers, seeded_departments):
    created = submit(client, student_headers, seeded_departments["hostel"].id, "Wing B corridor light",
                     floor_id=world["floors"]["B1"].id).json()
    response = client.get(HOSTEL_FEED, headers=student_headers)
    assert response.headers["X-Total-Count"] == "1"
    item = response.json()[0]
    assert set(item) == HOSTEL_FEED_ITEM_KEYS
    assert not FORBIDDEN_FEED_KEYS & set(item)
    assert (item["id"], item["hostel"], item["wing"], item["floor"]) == (created["id"], "Main Hostel", "Wing B", "Floor 1")


def test_student_cannot_select_a_hostel(client, world, student_headers):
    response = client.get(f"{HOSTEL_FEED}?hostel_id={world['main'].id}", headers=student_headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "hostel_selection_forbidden"
    assert client.get(f"{HOSTEL_FEED}?hostel_id=abc", headers=student_headers).status_code == 422


@pytest.mark.parametrize("state", ["none", "pending", "rejected", "inactive_floor", "inactive_verifier", "student_verifier"])
def test_students_without_a_verified_residence_get_residence_not_verified(
    client, db, world, student_b_user, student_b_headers, state,
):
    residence = world["floors"]["C1"]
    if state == "none":
        from app.models.student_residence import StudentResidence
        db.query(StudentResidence).filter_by(student_id=student_b_user.id).delete()
        db.commit()
    elif state in ("pending", "rejected"):
        set_residence(db, student_b_user, residence, world["hostel_staff"], status=state)
    elif state == "inactive_floor":
        residence.is_active = False
        db.commit()
    elif state == "inactive_verifier":
        world["hostel_staff"].is_active = False
        db.commit()
    elif state == "student_verifier":
        other = make_user(db, "other.student", "student")
        set_residence(db, student_b_user, residence, other)
    for query in ("", "?scope=wing", "?scope=floor"):
        response = client.get(HOSTEL_FEED + query, headers=student_b_headers)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "residence_not_verified"


def test_changing_residence_immediately_revokes_feed_access(client, world, student_headers):
    assert client.get(HOSTEL_FEED, headers=student_headers).status_code == 200
    changed = client.patch("/api/v1/users/me/residence", headers=student_headers,
                           json={"floor_id": world["floors"]["B1"].id})
    assert changed.status_code == 200 and changed.json()["status"] == "pending"
    response = client.get(HOSTEL_FEED, headers=student_headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "residence_not_verified"


def test_wing_and_floor_scopes_follow_the_verified_residence(
    client, db, world, student_b_user, student_b_headers, seeded_departments, student_headers,
):
    hostel = seeded_departments["hostel"].id
    set_residence(db, student_b_user, world["floors"]["B2"], world["hostel_staff"])  # Bob moves to B/2
    b2 = submit(client, student_b_headers, hostel, "Wing B floor 2 leak", floor_id=world["floors"]["B2"].id).json()
    b1 = submit(client, student_headers, hostel, "Wing B floor 1 leak", floor_id=world["floors"]["B1"].id).json()
    d2 = submit(client, student_headers, hostel, "Wing D floor 2 leak", floor_id=world["floors"]["D2"].id).json()
    assert {b2["publication_status"], b1["publication_status"], d2["publication_status"]} == {"published"}
    assert feed_ids(client.get(f"{HOSTEL_FEED}?scope=floor", headers=student_b_headers)) == {b2["id"]}
    assert feed_ids(client.get(f"{HOSTEL_FEED}?scope=wing", headers=student_b_headers)) == {b1["id"], b2["id"]}
    assert feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers)) == {b1["id"], b2["id"], d2["id"]}
    # Alice (A/1) has nothing in her own wing or floor.
    assert feed_ids(client.get(f"{HOSTEL_FEED}?scope=wing", headers=student_headers)) == set()


@pytest.mark.parametrize("corruption", ["three_floors", "mixed_floor_levels", "other_hostel_floor", "inactive_group"])
def test_hmc_group_data_no_longer_affects_the_feed(client, db, world, student_headers, seeded_departments, corruption):
    """Groups are kept in the database but are not read for visibility (S4-09)."""
    item = submit(client, student_headers, seeded_departments["hostel"].id, "Wing A bulb fused",
                  floor_id=world["floors"]["A1"].id).json()
    group = world["groups"]["AB1"]
    floors = world["floors"]
    if corruption == "three_floors":
        db.add(HMCGroupFloor(hmc_group_id=group.id, floor_id=floors["D1"].id))
    elif corruption == "mixed_floor_levels":
        db.query(HMCGroupFloor).filter_by(floor_id=floors["B1"].id).delete()
        db.add(HMCGroupFloor(hmc_group_id=group.id, floor_id=floors["A2"].id))
    elif corruption == "other_hostel_floor":
        db.query(HMCGroupFloor).filter_by(floor_id=floors["B1"].id).delete()
        db.query(HMCGroupFloor).filter_by(floor_id=floors["N1"].id).delete()
        db.add(HMCGroupFloor(hmc_group_id=group.id, floor_id=floors["N1"].id))
    elif corruption == "inactive_group":
        group.is_active = False
    db.commit()
    assert feed_ids(client.get(HOSTEL_FEED, headers=student_headers)) == {item["id"]}


# --- Removed Sprint 3 routes ---------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/hmc/complaints/{cid}/audiences"),
    ("post", "/api/v1/hmc/complaints/{cid}/audiences"),
    ("post", "/api/v1/hmc/complaints/{cid}/audiences/{gid}/revoke"),
    ("get", "/api/v1/hmc/groups"),
    ("patch", "/api/v1/hmc/groups/{gid}/moderators/{uid}"),
])
def test_removed_hmc_group_and_audience_routes_return_404(
    client, world, student_headers, admin_headers, seeded_departments, method, path,
):
    cid = submit(client, student_headers, seeded_departments["hostel"].id, "Floor 1 common water supply",
                 floor_id=world["floors"]["A1"].id).json()["id"]
    url = path.format(cid=cid, gid=world["groups"]["C1"].id, uid=world["hostel_staff"].id)
    response = getattr(client, method)(url, headers=admin_headers, **({} if method == "get" else {"json": {}}))
    assert response.status_code == 404


# --- Moderation --------------------------------------------------------------------

def test_report_about_another_hostel_requires_review_then_publishes_hostel_wide(
    client, world, nh_resident, nh_headers, student_headers, student_b_headers, admin_headers, seeded_departments,
):
    response = submit(client, nh_headers, seeded_departments["it"].id, "Wing C electrical issue",
                      floor_id=world["floors"]["C1"].id)
    assert response.status_code == 201, response.text
    complaint_id = response.json()["id"]
    assert response.json()["publication_status"] == "pending_review"
    assert complaint_id not in feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers))

    queue = client.get(QUEUE, headers=admin_headers)
    assert queue.status_code == 200
    queue_item = next(item for item in queue.json() if item["id"] == complaint_id)
    assert queue_item["reporter_id"] == nh_resident.id
    assert "responsible_hmc_group_id" not in queue_item

    approved = client.post(decision(complaint_id), json={"decision": "approved"}, headers=admin_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["publication_status"] == "published"
    # Visible to every Main Hostel resident, and not to the reporter's own (other) hostel.
    assert complaint_id in feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers))
    assert complaint_id in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))
    assert complaint_id not in feed_ids(client.get(HOSTEL_FEED, headers=nh_headers))
    detail = client.get(f"/api/v1/feeds/items/{complaint_id}", headers=student_b_headers)
    assert detail.status_code == 200
    assert not FORBIDDEN_FEED_KEYS & set(detail.json())
    assert client.post(decision(complaint_id), json={"decision": "approved"}, headers=admin_headers).status_code == 409


def test_rejection_requires_reason_and_never_publishes(
    client, db, world, nh_headers, student_b_headers, admin_headers, seeded_departments,
):
    cid = submit(client, nh_headers, seeded_departments["hostel"].id, "Wing C suspicious report",
                 floor_id=world["floors"]["C1"].id).json()["id"]
    assert client.post(decision(cid), json={"decision": "rejected"}, headers=admin_headers).status_code == 422
    rejected = client.post(decision(cid), headers=admin_headers,
                           json={"decision": "rejected", "note": "Location/details could not be substantiated."})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["publication_status"] == "rejected"
    assert db.query(ComplaintPublicationAudit).filter_by(complaint_id=cid, action="rejected").count() == 1
    assert db.query(ComplaintHMCAudience).filter_by(complaint_id=cid).count() == 0
    assert cid not in feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers))


def test_students_cannot_read_the_queue_or_moderate(client, world, student_headers, seeded_departments):
    assert client.get(QUEUE, headers=student_headers).status_code == 403
    cid = submit(client, student_headers, seeded_departments["it"].id, "Outside wing report",
                 floor_id=world["floors"]["C1"].id).json()["id"]
    assert client.post(decision(cid), json={"decision": "approved"}, headers=student_headers).status_code == 403
    assert client.post(f"/api/v1/hmc/complaints/{cid}/unpublish", json={"note": "Nope nope"},
                       headers=student_headers).status_code == 403


def test_hostel_staff_moderate_and_other_department_staff_cannot(
    client, world, nh_headers, seeded_departments,
):
    it_staff, hostel_staff = world["it_staff"], world["hostel_staff"]
    cid = submit(client, nh_headers, seeded_departments["it"].id, "Wing C router report",
                 floor_id=world["floors"]["C1"].id).json()["id"]
    # IT staff own the complaint's workflow but have no hostel publication authority.
    assert client.get(QUEUE, headers=headers_for(it_staff)).status_code == 403
    assert client.post(decision(cid), json={"decision": "approved"}, headers=headers_for(it_staff)).status_code == 403
    # Hostel-department staff review it without any designation step.
    queue = client.get(QUEUE, headers=headers_for(hostel_staff))
    assert queue.status_code == 200 and {item["id"] for item in queue.json()} == {cid}
    assert client.post(decision(cid), json={"decision": "approved"}, headers=headers_for(hostel_staff)).status_code == 200


def test_unmapped_requests_are_admin_only(
    client, db, world, admin_headers, student_headers, nh_headers, seeded_departments, monkeypatch,
):
    hostel = seeded_departments["hostel"].id
    c1 = submit(client, nh_headers, hostel, "Wing C door broken", floor_id=world["floors"]["C1"].id).json()["id"]
    d2 = submit(client, nh_headers, hostel, "Wing D door broken", floor_id=world["floors"]["D2"].id).json()["id"]
    monkeypatch.setattr(settings, "HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID", False)  # legacy data
    unmapped = submit(client, student_headers, hostel, "Unlocated door broken").json()["id"]
    staff = headers_for(world["hostel_staff"])
    assert {i["id"] for i in client.get(QUEUE, headers=staff).json()} == {c1, d2}
    assert {c1, d2, unmapped} <= {i["id"] for i in client.get(QUEUE, headers=admin_headers).json()}
    assert client.post(decision(unmapped), json={"decision": "approved"}, headers=staff).status_code == 403
    # Approval needs an active canonical floor.
    assert client.post(decision(unmapped), json={"decision": "approved"}, headers=admin_headers).status_code == 409


def test_unpublish_records_audit_and_removes_item_from_feeds(
    client, db, world, student_headers, admin_headers, seeded_departments,
):
    dep = seeded_departments["it"].id
    cid = submit(client, student_headers, dep, "Campus network outage").json()["id"]
    assert cid in feed_ids(client.get(dept_feed(dep), headers=student_headers))
    result = client.post(f"/api/v1/hmc/complaints/{cid}/unpublish",
                         json={"note": "Contains inappropriate public-facing content."}, headers=admin_headers)
    assert result.status_code == 200, result.text
    assert result.json()["publication_status"] == "rejected"
    assert db.query(ComplaintPublicationAudit).filter_by(complaint_id=cid, action="unpublished").count() == 1
    assert cid not in feed_ids(client.get(dept_feed(dep), headers=student_headers))

    note = {"note": "Duplicate of an older report."}
    located = submit(client, student_headers, seeded_departments["hostel"].id, "Wing A noisy pump",
                     floor_id=world["floors"]["A1"].id).json()["id"]
    assert client.post(f"/api/v1/hmc/complaints/{located}/unpublish", json=note,
                       headers=headers_for(world["it_staff"])).status_code == 403
    assert client.post(f"/api/v1/hmc/complaints/{located}/unpublish", json=note,
                       headers=headers_for(world["hostel_staff"])).status_code == 200
    assert located not in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))
    # Hostel staff cannot unpublish a department-wide complaint; only an admin can.
    campus = submit(client, student_headers, dep, "Campus printer jam").json()["id"]
    assert client.post(f"/api/v1/hmc/complaints/{campus}/unpublish", json=note,
                       headers=headers_for(world["hostel_staff"])).status_code == 403


@pytest.mark.parametrize("level", ["floor", "wing"])
def test_complaints_on_a_deactivated_location_leave_every_feed(
    client, db, world, admin_headers, student_headers, student_b_headers, seeded_departments, level,
):
    """Bob reports C/1; once that floor (or Wing C) is deactivated, nobody sees it in a feed or by ID."""
    cid = submit(client, student_b_headers, seeded_departments["hostel"].id, "Wing C fan broken",
                 floor_id=world["floors"]["C1"].id).json()["id"]
    staff = headers_for(world["hostel_staff"])
    for headers in (student_headers, staff, admin_headers):
        assert cid in feed_ids(client.get(HOSTEL_FEED, headers=headers))
    target = world["floors"]["C1"] if level == "floor" else world["wings"]["C"]
    target.is_active = False
    db.commit()
    for headers in (student_headers, staff, admin_headers):
        assert cid not in feed_ids(client.get(HOSTEL_FEED, headers=headers))
        assert client.get(f"/api/v1/feeds/items/{cid}", headers=headers).status_code == 404
    assert cid not in duplicate_ids(client, student_headers, "Wing C fan broken",
                                    "A detailed report describing the observed campus issue.")
    target.is_active = True  # reactivation brings it back
    db.commit()
    assert cid in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))


# --- Hostel feed: staff and admin -------------------------------------------------

def test_hostel_staff_and_admin_see_every_hostel_and_can_filter_by_hostel(
    client, db, world, admin_headers, student_headers, nh_headers, seeded_departments,
):
    hostel = seeded_departments["hostel"].id
    main_item = submit(client, student_headers, hostel, "Wing A tap leak", floor_id=world["floors"]["A1"].id).json()["id"]
    pending = submit(client, nh_headers, hostel, "Wing C tap leak", floor_id=world["floors"]["C1"].id).json()["id"]
    new_item = submit(client, nh_headers, hostel, "Wing N tap leak", floor_id=world["floors"]["N1"].id).json()["id"]

    for headers in (admin_headers, headers_for(world["hostel_staff"])):
        response = client.get(HOSTEL_FEED, headers=headers)
        assert feed_ids(response) == {main_item, new_item}
        assert response.headers["X-Total-Count"] == "2"
        assert all(set(item) == HOSTEL_FEED_ITEM_KEYS for item in response.json())
        assert pending not in feed_ids(response)
        assert feed_ids(client.get(f"{HOSTEL_FEED}?hostel_id={world['new'].id}", headers=headers)) == {new_item}
        assert feed_ids(client.get(f"{HOSTEL_FEED}?hostel_id={world['main'].id}", headers=headers)) == {main_item}
        missing = client.get(f"{HOSTEL_FEED}?hostel_id=999999", headers=headers)
        assert missing.status_code == 404 and missing.json()["detail"]["code"] == "hostel_not_found"
        scoped = client.get(f"{HOSTEL_FEED}?scope=wing", headers=headers)
        assert scoped.status_code == 403 and scoped.json()["detail"]["code"] == "scope_selection_forbidden"

    world["new"].is_active = False
    db.commit()
    inactive = client.get(f"{HOSTEL_FEED}?hostel_id={world['new'].id}", headers=admin_headers)
    assert inactive.status_code == 404 and inactive.json()["detail"]["code"] == "hostel_not_found"


def test_other_staff_cannot_read_the_hostel_feed(client, world, staff_headers):
    assert client.get(HOSTEL_FEED, headers=headers_for(world["it_staff"])).status_code == 403
    assert client.get(HOSTEL_FEED, headers=staff_headers).status_code == 403  # no department
    assert client.get(HOSTEL_FEED).status_code == 401


def test_missing_or_inactive_hostel_department_returns_404(client, db, world, admin_headers, seeded_departments):
    seeded_departments["hostel"].is_active = False
    db.commit()
    assert client.get(HOSTEL_FEED, headers=admin_headers).status_code == 404


def test_hostel_staff_lose_feed_access_if_the_hostel_department_is_inactive(client, db, world, seeded_departments):
    seeded_departments["hostel"].is_active = False
    db.commit()
    assert client.get(HOSTEL_FEED, headers=headers_for(world["hostel_staff"])).status_code == 404


# --- Cross-department hostel complaints ---------------------------------------------

def test_hostel_specific_it_complaint_stays_hostel_restricted_but_keeps_its_it_workflow(
    client, world, student_headers, student_b_headers, nh_headers, seeded_departments,
):
    it = seeded_departments["it"].id
    created = submit(client, student_headers, it, "Wing A Wi-Fi access point dead",
                     floor_id=world["floors"]["A1"].id).json()
    cid = created["id"]
    assert created["department_id"] == it
    assert created["visibility_scope"] == "hmc_group_public"  # stored value kept; means hostel-scoped
    assert created["publication_status"] == "published"

    assert cid not in feed_ids(client.get(dept_feed(it), headers=student_b_headers))
    assert cid in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))
    assert cid in feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers))  # same hostel
    assert cid not in feed_ids(client.get(HOSTEL_FEED, headers=nh_headers))
    assert client.get(f"/api/v1/feeds/items/{cid}", headers=nh_headers).status_code == 404

    # IT staff still handle it through the normal department queue.
    it_headers = headers_for(world["it_staff"])
    assert cid in {i["id"] for i in client.get("/api/v1/staff/complaints", headers=it_headers).json()}
    moved = client.patch(f"/api/v1/staff/complaints/{cid}/status", headers=it_headers,
                         json={"status": "in_progress", "remark": "Technician assigned."})
    assert moved.status_code == 200, moved.text
    # ...but the IT queue does not grant hostel feed access or item visibility.
    assert client.get(f"/api/v1/feeds/items/{cid}", headers=it_headers).status_code == 404
    feed = client.get(HOSTEL_FEED, headers=student_headers).json()
    assert next(item for item in feed if item["id"] == cid)["status"] == "in_progress"


# --- Legacy locations --------------------------------------------------------------

def test_legacy_records_are_never_exposed_even_if_marked_published(
    client, db, world, student_user, student_b_user, student_headers, admin_headers, seeded_departments,
):
    description = "Legacy text-only hostel location from before canonical floors existed."
    legacy = Complaint(
        title="Legacy Wing A leak", description=description, department_id=seeded_departments["hostel"].id,
        created_by_id=student_b_user.id, is_public=True, hostel="Main Hostel", wing="Wing A", floor="Floor 1",
        visibility_scope="hmc_group_public", publication_status="published",
    )
    db.add(legacy)
    db.flush()
    # Even a stray audience row cannot expose a record that has no canonical floor.
    from app.models.complaint_hmc_audience import ComplaintHMCAudience as Audience
    db.add(Audience(complaint_id=legacy.id, hmc_group_id=world["groups"]["AB1"].id,
                    source="responsible_group", decided_by_id=student_b_user.id))
    db.commit()
    assert legacy.id not in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))
    assert legacy.id not in feed_ids(client.get(HOSTEL_FEED, headers=admin_headers))
    assert client.get(f"/api/v1/feeds/items/{legacy.id}", headers=student_headers).status_code == 404
    assert legacy.id not in duplicate_ids(client, student_headers, "Legacy Wing A leak", description)
    # The original text values are preserved for verified backfill.
    detail = client.get(f"/api/v1/complaints/{legacy.id}", headers=headers_for(student_b_user)).json()
    assert (detail["hostel"], detail["wing"], detail["floor"], detail["location"]) == ("Main Hostel", "Wing A", "Floor 1", None)


# --- Duplicate suggestions -----------------------------------------------------------

DUP_TEXT = "The corridor router is offline and the network connectivity is disrupted all day."


def test_duplicate_candidates_follow_publication_and_hostel_rules(
    client, db, world, student_user, student_b_user, nh_resident, student_headers, student_b_headers,
    nh_headers, admin_headers, seeded_departments,
):
    it, hostel = seeded_departments["it"].id, seeded_departments["hostel"].id
    floors = world["floors"]
    title = "Corridor router offline"
    ids = {
        "alice_own_private": submit(client, student_headers, it, title, is_public=False, description=DUP_TEXT),
        "bob_private": submit(client, student_b_headers, it, title, is_public=False, description=DUP_TEXT),
        "bob_department_public": submit(client, student_b_headers, it, title, description=DUP_TEXT),
        "bob_own_hostel": submit(client, student_b_headers, hostel, title, description=DUP_TEXT, floor_id=floors["C1"].id),
        "nh_pending_in_main": submit(client, nh_headers, hostel, title, description=DUP_TEXT, floor_id=floors["B1"].id),
        "nh_rejected_in_main": submit(client, nh_headers, hostel, title, description=DUP_TEXT, floor_id=floors["A1"].id),
        "nh_own_hostel": submit(client, nh_headers, hostel, title, description=DUP_TEXT, floor_id=floors["N1"].id),
        "bob_legacy_text": submit(client, student_b_headers, it, title, description=DUP_TEXT, hostel="Main Hostel"),
    }
    ids = {key: response.json()["id"] for key, response in ids.items()}
    client.post(decision(ids["nh_rejected_in_main"]), headers=admin_headers,
                json={"decision": "rejected", "note": "Not substantiated."})

    from app.services.duplicate_service import visible_duplicate_candidates

    def visible(user):
        return {c.id for c in visible_duplicate_candidates(db, user)}

    assert visible(student_user) == {ids["alice_own_private"], ids["bob_department_public"], ids["bob_own_hostel"]}

    # Approving the pending Main Hostel report makes it a candidate for Main Hostel residents.
    client.post(decision(ids["nh_pending_in_main"]), headers=admin_headers, json={"decision": "approved"})
    alice_visible = visible(student_user)
    assert alice_visible == {
        ids["alice_own_private"], ids["bob_department_public"], ids["bob_own_hostel"], ids["nh_pending_in_main"],
    }
    matches = client.post("/api/v1/complaints/duplicate-suggestions", headers=student_headers,
                          json={"title": title, "description": DUP_TEXT}).json()["matches"]
    assert {m["id"] for m in matches} <= alice_visible and len(matches) == 3  # top 3 of the visible set
    nh_visible = visible(nh_resident)
    assert ids["nh_own_hostel"] in nh_visible
    assert not nh_visible & {ids["bob_own_hostel"], ids["alice_own_private"], ids["bob_private"]}
    assert ids["nh_own_hostel"] not in visible(student_b_user)
    for match in matches:
        assert set(match) == {"id", "title", "department_id", "department_name", "status", "similarity_score"}


def test_duplicate_threshold_and_algorithm_are_preserved(client, world, student_headers):
    response = client.post("/api/v1/complaints/duplicate-suggestions", headers=student_headers,
                           json={"title": "Anything at all", "description": "Some description text here."})
    assert response.status_code == 200
    assert response.json()["threshold"] == 0.375


def test_same_hostel_residents_receive_duplicate_suggestions(
    client, db, world, student_b_user, student_headers, student_b_headers, seeded_departments,
):
    set_residence(db, student_b_user, world["floors"]["B1"], world["hostel_staff"])
    created = submit(client, student_headers, seeded_departments["it"].id, "Wing A router outage",
                     floor_id=world["floors"]["A1"].id)
    assert created.json()["publication_status"] == "published"
    assert created.json()["id"] in duplicate_ids(client, student_b_headers, "Wing A router outage",
                                                 "A detailed report describing the observed campus issue.")


def test_duplicate_suggestions_do_not_leak_published_items_across_hostels(
    client, world, student_headers, nh_headers, seeded_departments,
):
    created = submit(client, student_headers, seeded_departments["it"].id, "Wing A router offline",
                     floor_id=world["floors"]["A1"].id)
    assert created.json()["publication_status"] == "published"
    assert created.json()["id"] not in duplicate_ids(
        client, nh_headers, "Wing A router offline",
        "The Wing A router is offline and campus network connectivity is disrupted.",
    )
