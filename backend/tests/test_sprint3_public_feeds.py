"""Sprint 3 public feeds, HMC visibility, moderation and duplicate-candidate security.

Ports PR #46's public-feed regression tests to the canonical hostel hierarchy
and contract routes, and adds explicit shared-floor audience, cross-department
and legacy-location coverage.
"""
import pytest

from app.core.config import settings
from app.models.complaint import Complaint
from app.models.complaint_hmc_audience import ComplaintHMCAudience
from app.models.complaint_publication_audit import ComplaintPublicationAudit
from app.models.hmc_group import HMCGroupFloor
from app.models.hmc_group_moderator import HMCGroupModerator
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


def audiences(complaint_id):
    return f"/api/v1/hmc/complaints/{complaint_id}/audiences"


@pytest.fixture
def world(db, seeded_departments, student_user, student_b_user):
    return build_world(db, seeded_departments, student_user, student_b_user)


# --- Department feed -----------------------------------------------------------

def test_department_feed_excludes_hmc_and_never_returns_description_or_reporter_identity(
    client, world, student_headers, seeded_departments,
):
    dep = seeded_departments["it"].id
    department_public = submit(client, student_headers, dep, "Campus Wi-Fi outage")
    hmc = submit(client, student_headers, dep, "Wing C access point broken", floor_id=world["floors"]["C1"].id)
    assert department_public.status_code == 201, department_public.text
    assert department_public.json()["publication_status"] == "published"
    assert hmc.status_code == 201, hmc.text
    assert hmc.json()["publication_status"] == "pending_review"

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
    client, db, world, seeded_departments, student_headers, student_b_headers,
):
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


def test_verified_member_auto_publishes_to_their_own_group_only(
    client, db, world, student_headers, seeded_departments,
):
    response = submit(client, student_headers, seeded_departments["hostel"].id,
                      "Wing A light issue", floor_id=world["floors"]["A1"].id)
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["publication_status"] == "published"
    assert item["feed_review_status"] == "auto_approved"
    assert item["location"] == {"hostel": "Main Hostel", "wing": "Wing A", "floor": "Floor 1"}
    rows = db.query(ComplaintHMCAudience).filter_by(complaint_id=item["id"]).all()
    assert [(row.hmc_group_id, row.source) for row in rows] == [(world["groups"]["AB1"].id, "responsible_group")]
    assert item["id"] in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))


def test_reporting_another_wing_keeps_the_affected_location_and_needs_review(
    client, world, student_headers, seeded_departments,
):
    # Alice lives on A/1 (verified) but reports C/1: the location is C/1, not her residence.
    response = submit(client, student_headers, seeded_departments["hostel"].id,
                      "Wing C washroom leak", floor_id=world["floors"]["C1"].id)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["floor_id"] == world["floors"]["C1"].id
    assert data["location"] == {"hostel": "Main Hostel", "wing": "Wing C", "floor": "Floor 1"}
    assert data["publication_status"] == "pending_review"


def test_configured_floor_without_an_hmc_group_stays_pending_mapping(
    client, world, student_headers, seeded_departments,
):
    response = submit(client, student_headers, seeded_departments["hostel"].id,
                      "Wing D floor 3 ventilation", floor_id=world["floors"]["D3"].id)
    assert response.status_code == 201, response.text
    assert response.json()["publication_status"] == "pending_mapping"
    assert response.json()["feed_review_status"] == "pending"
    assert response.json()["id"] not in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))


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


def test_hostel_complaint_floor_requirement_can_be_enforced(
    client, world, student_headers, seeded_departments, monkeypatch,
):
    monkeypatch.setattr(settings, "HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID", True)
    missing = submit(client, student_headers, seeded_departments["hostel"].id, "Hostel fan broken")
    assert missing.status_code == 422
    located = submit(client, student_headers, seeded_departments["hostel"].id, "Hostel fan broken",
                     floor_id=world["floors"]["A1"].id)
    assert located.status_code == 201
    # Other departments still accept unlocated complaints.
    assert submit(client, student_headers, seeded_departments["it"].id, "Campus Wi-Fi down").status_code == 201


def test_inactive_floor_is_rejected_on_submission(client, db, world, student_headers, seeded_departments):
    world["wings"]["D"].is_active = False
    db.commit()
    response = submit(client, student_headers, seeded_departments["hostel"].id, "Inactive wing",
                      floor_id=world["floors"]["D2"].id)
    assert response.status_code == 422


# --- Hostel feed: students -----------------------------------------------------------

def test_different_hmc_groups_never_see_each_others_complaints(
    client, world, student_headers, student_b_headers, seeded_departments,
):
    alice_item = submit(client, student_headers, seeded_departments["hostel"].id, "Wing A geyser broken",
                        floor_id=world["floors"]["A1"].id).json()
    bob_item = submit(client, student_b_headers, seeded_departments["hostel"].id, "Wing C geyser broken",
                      floor_id=world["floors"]["C1"].id).json()
    assert alice_item["publication_status"] == bob_item["publication_status"] == "published"
    assert feed_ids(client.get(HOSTEL_FEED, headers=student_headers)) == {alice_item["id"]}
    assert feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers)) == {bob_item["id"]}
    # Guessing the other group's detail ID returns 404.
    assert client.get(f"/api/v1/feeds/items/{bob_item['id']}", headers=student_headers).status_code == 404
    assert client.get(f"/api/v1/feeds/items/{alice_item['id']}", headers=student_headers).status_code == 200


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


@pytest.mark.parametrize("state", ["none", "pending", "rejected", "unmapped_floor", "inactive_verifier", "student_verifier"])
def test_students_without_a_valid_verified_group_get_residence_not_verified(
    client, db, world, student_b_user, student_b_headers, state,
):
    residence = world["floors"]["C1"]
    if state == "none":
        from app.models.student_residence import StudentResidence
        db.query(StudentResidence).filter_by(student_id=student_b_user.id).delete()
        db.commit()
    elif state in ("pending", "rejected"):
        set_residence(db, student_b_user, residence, world["hostel_staff"], status=state)
    elif state == "unmapped_floor":
        set_residence(db, student_b_user, world["floors"]["D1"], world["hostel_staff"])
    elif state == "inactive_verifier":
        world["hostel_staff"].is_active = False
        db.commit()
    elif state == "student_verifier":
        other = make_user(db, "other.student", "student")
        set_residence(db, student_b_user, residence, other)
    response = client.get(HOSTEL_FEED, headers=student_b_headers)
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


def test_hmc_membership_uses_the_verified_floor_not_the_wing_alone(
    client, db, world, student_b_user, student_b_headers, seeded_departments, student_headers,
):
    # Wing B belongs to AB1 on floor 1 and BD2 on floor 2.
    set_residence(db, student_b_user, world["floors"]["B2"], world["hostel_staff"])
    floor2 = submit(client, student_b_headers, seeded_departments["hostel"].id, "Wing B floor 2 leak",
                    floor_id=world["floors"]["B2"].id).json()
    assert floor2["publication_status"] == "published"
    floor1 = submit(client, student_headers, seeded_departments["hostel"].id, "Wing B floor 1 leak",
                    floor_id=world["floors"]["B1"].id).json()
    assert feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers)) == {floor2["id"]}
    assert feed_ids(client.get(HOSTEL_FEED, headers=student_headers)) == {floor1["id"]}


@pytest.mark.parametrize("corruption", ["three_floors", "mixed_floor_levels", "other_hostel_floor", "inactive_group"])
def test_corrupt_hmc_group_fails_closed(client, db, world, student_headers, corruption):
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
    response = client.get(HOSTEL_FEED, headers=student_headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "residence_not_verified"


# --- Shared-floor audiences ----------------------------------------------------------

def test_floor_level_neighbours_do_not_see_complaints_without_an_explicit_audience(
    client, db, world, student_headers, student_b_headers, admin_headers, seeded_departments,
):
    """AB1 and C1 share floor level 1; publishing to AB1 must not broadcast to C1."""
    created = submit(client, student_headers, seeded_departments["hostel"].id,
                     "Floor 1 common water supply", floor_id=world["floors"]["A1"].id).json()
    cid = created["id"]
    assert created["publication_status"] == "published"
    assert cid in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))
    assert cid not in feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers))
    assert cid not in duplicate_ids(client, student_b_headers, "Floor 1 common water supply",
                                    "A detailed report describing the observed campus issue.")

    grant = client.post(audiences(cid), headers=admin_headers,
                        json={"hmc_group_id": world["groups"]["C1"].id, "note": "Shared floor water tank."})
    assert grant.status_code == 200, grant.text
    assert {(a["hmc_group_id"], a["source"]) for a in grant.json()} == {
        (world["groups"]["AB1"].id, "responsible_group"), (world["groups"]["C1"].id, "shared_floor"),
    }
    assert cid in feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers))
    assert cid in duplicate_ids(client, student_b_headers, "Floor 1 common water supply",
                                "A detailed report describing the observed campus issue.")
    assert db.query(ComplaintPublicationAudit).filter_by(complaint_id=cid, action="audience_added").count() == 1

    revoke = client.post(f"{audiences(cid)}/{world['groups']['C1'].id}/revoke", headers=admin_headers,
                         json={"note": "Tank was only on Wing A side."})
    assert revoke.status_code == 200, revoke.text
    assert cid not in feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers))
    assert db.query(ComplaintPublicationAudit).filter_by(complaint_id=cid, action="audience_removed").count() == 1


def test_shared_floor_audience_is_limited_to_the_same_hostel_floor_level(
    client, world, student_headers, admin_headers, seeded_departments,
):
    cid = submit(client, student_headers, seeded_departments["hostel"].id, "Floor 1 corridor flooding",
                 floor_id=world["floors"]["A1"].id).json()["id"]
    groups = world["groups"]
    for group_key in ("BD2", "N1", "AB1"):  # other level, other hostel, responsible group itself
        response = client.post(audiences(cid), headers=admin_headers,
                               json={"hmc_group_id": groups[group_key].id, "note": "Attempted share."})
        assert response.status_code == 422, (group_key, response.text)
    duplicate = {"hmc_group_id": groups["C1"].id, "note": "Shared floor."}
    assert client.post(audiences(cid), headers=admin_headers, json=duplicate).status_code == 200
    assert client.post(audiences(cid), headers=admin_headers, json=duplicate).status_code == 409
    # The responsible group is removed only by unpublishing.
    revoke = client.post(f"{audiences(cid)}/{groups['AB1'].id}/revoke", headers=admin_headers, json={"note": "No."})
    assert revoke.status_code == 409


def test_unpublished_or_pending_complaints_cannot_be_shared(
    client, world, student_headers, admin_headers, seeded_departments,
):
    pending = submit(client, student_headers, seeded_departments["hostel"].id, "Wing C report",
                     floor_id=world["floors"]["C1"].id).json()
    response = client.post(audiences(pending["id"]), headers=admin_headers,
                           json={"hmc_group_id": world["groups"]["AB1"].id, "note": "Share early."})
    assert response.status_code == 409


def test_shared_floor_audience_requires_moderation_authority_over_both_groups(
    client, db, world, admin_user, student_headers, seeded_departments,
):
    cid = submit(client, student_headers, seeded_departments["hostel"].id, "Floor 1 stairwell light",
                 floor_id=world["floors"]["A1"].id).json()["id"]
    body = {"hmc_group_id": world["groups"]["C1"].id, "note": "Shared stairwell."}
    hostel_staff, it_staff = world["hostel_staff"], world["it_staff"]

    # Students, department staff (including Hostel staff) without designation: forbidden.
    for user_headers in (student_headers, headers_for(hostel_staff), headers_for(it_staff)):
        assert client.post(audiences(cid), headers=user_headers, json=body).status_code == 403

    # A moderator of only the responsible group cannot widen into another group's feed.
    db.add(HMCGroupModerator(hmc_group_id=world["groups"]["AB1"].id, user_id=hostel_staff.id, assigned_by_user_id=admin_user.id))
    db.commit()
    assert client.post(audiences(cid), headers=headers_for(hostel_staff), json=body).status_code == 403
    db.add(HMCGroupModerator(hmc_group_id=world["groups"]["C1"].id, user_id=hostel_staff.id, assigned_by_user_id=admin_user.id))
    db.commit()
    assert client.post(audiences(cid), headers=headers_for(hostel_staff), json=body).status_code == 200


# --- Moderation --------------------------------------------------------------------

def test_outside_group_report_requires_review_and_publishes_to_the_responsible_group_only(
    client, world, student_user, student_headers, student_b_headers, admin_headers, seeded_departments,
):
    response = submit(client, student_headers, seeded_departments["it"].id, "Wing C electrical issue",
                      floor_id=world["floors"]["C1"].id)
    assert response.status_code == 201, response.text
    complaint_id = response.json()["id"]
    assert response.json()["publication_status"] == "pending_review"
    assert complaint_id not in feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers))

    queue = client.get(QUEUE, headers=admin_headers)
    assert queue.status_code == 200
    queue_item = next(item for item in queue.json() if item["id"] == complaint_id)
    assert queue_item["reporter_id"] == student_user.id
    assert queue_item["responsible_hmc_group_id"] == world["groups"]["C1"].id

    approved = client.post(decision(complaint_id), json={"decision": "approved"}, headers=admin_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["publication_status"] == "published"
    assert complaint_id in feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers))
    # The reporter's own group (AB1) is not an audience.
    assert complaint_id not in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))
    detail = client.get(f"/api/v1/feeds/items/{complaint_id}", headers=student_b_headers)
    assert detail.status_code == 200
    assert not FORBIDDEN_FEED_KEYS & set(detail.json())
    assert client.post(decision(complaint_id), json={"decision": "approved"}, headers=admin_headers).status_code == 409


def test_rejection_requires_reason_and_never_publishes(
    client, db, world, student_headers, student_b_headers, admin_headers, seeded_departments,
):
    cid = submit(client, student_headers, seeded_departments["hostel"].id, "Wing C suspicious report",
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
    assert client.get("/api/v1/hmc/groups", headers=student_headers).status_code == 403


def test_department_staff_cannot_moderate_but_designated_hmc_moderator_can(
    client, world, admin_headers, student_headers, seeded_departments,
):
    it_staff, hostel_staff = world["it_staff"], world["hostel_staff"]
    cid = submit(client, student_headers, seeded_departments["it"].id, "Wing C router report",
                 floor_id=world["floors"]["C1"].id).json()["id"]
    # IT staff own the complaint's workflow but have no HMC publication authority.
    assert client.get(QUEUE, headers=headers_for(it_staff)).status_code == 403
    assert client.post(decision(cid), json={"decision": "approved"}, headers=headers_for(it_staff)).status_code == 403
    assert client.post(decision(cid), json={"decision": "approved"}, headers=headers_for(hostel_staff)).status_code == 403

    assign = client.patch(f"/api/v1/hmc/groups/{world['groups']['C1'].id}/moderators/{it_staff.id}",
                          json={"assigned": True}, headers=admin_headers)
    assert assign.status_code == 200, assign.text
    queue = client.get(QUEUE, headers=headers_for(it_staff))
    assert queue.status_code == 200 and {item["id"] for item in queue.json()} == {cid}
    assert client.get("/api/v1/hmc/groups", headers=headers_for(it_staff)).status_code == 200
    assert client.post(decision(cid), json={"decision": "approved"}, headers=headers_for(it_staff)).status_code == 200

    # Only admins designate moderators.
    assert client.patch(f"/api/v1/hmc/groups/{world['groups']['C1'].id}/moderators/{hostel_staff.id}",
                        json={"assigned": True}, headers=headers_for(it_staff)).status_code == 403


def test_moderators_only_see_their_groups_and_unmapped_requests_are_admin_only(
    client, db, world, admin_user, admin_headers, student_headers, seeded_departments,
):
    hostel = seeded_departments["hostel"].id
    c1 = submit(client, student_headers, hostel, "Wing C door broken", floor_id=world["floors"]["C1"].id).json()["id"]
    bd2 = submit(client, student_headers, hostel, "Wing D door broken", floor_id=world["floors"]["D2"].id).json()["id"]
    unmapped = submit(client, student_headers, hostel, "Unlocated door broken").json()["id"]
    moderator = world["hostel_staff"]
    db.add(HMCGroupModerator(hmc_group_id=world["groups"]["C1"].id, user_id=moderator.id, assigned_by_user_id=admin_user.id))
    db.commit()
    assert {i["id"] for i in client.get(QUEUE, headers=headers_for(moderator)).json()} == {c1}
    assert {c1, bd2, unmapped} <= {i["id"] for i in client.get(QUEUE, headers=admin_headers).json()}
    assert client.post(decision(bd2), json={"decision": "approved"}, headers=headers_for(moderator)).status_code == 403
    # Approval needs a valid canonical floor and group mapping.
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

    hmc = submit(client, student_headers, seeded_departments["hostel"].id, "Wing A noisy pump",
                 floor_id=world["floors"]["A1"].id).json()["id"]
    assert client.post(f"/api/v1/hmc/complaints/{hmc}/unpublish", json={"note": "Duplicate of an older report."},
                       headers=headers_for(world["hostel_staff"])).status_code == 403
    assert client.post(f"/api/v1/hmc/complaints/{hmc}/unpublish", json={"note": "Duplicate of an older report."},
                       headers=admin_headers).status_code == 200
    assert hmc not in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))


# --- Hostel feed: staff and admin -------------------------------------------------

def test_hostel_staff_and_admin_see_authorized_items_and_can_filter_by_hostel(
    client, db, world, admin_headers, student_headers, seeded_departments,
):
    hostel = seeded_departments["hostel"].id
    main_item = submit(client, student_headers, hostel, "Wing A tap leak", floor_id=world["floors"]["A1"].id).json()["id"]
    pending = submit(client, student_headers, hostel, "Wing C tap leak", floor_id=world["floors"]["C1"].id).json()["id"]
    newcomer = make_user(db, "nh.resident", "student")
    set_residence(db, newcomer, world["floors"]["N1"], world["hostel_staff"])
    new_item = submit(client, headers_for(newcomer), hostel, "Wing N tap leak", floor_id=world["floors"]["N1"].id).json()["id"]

    for headers in (admin_headers, headers_for(world["hostel_staff"])):
        response = client.get(HOSTEL_FEED, headers=headers)
        assert feed_ids(response) == {main_item, new_item}
        assert response.headers["X-Total-Count"] == "2"
        assert all(set(item) == HOSTEL_FEED_ITEM_KEYS for item in response.json())
        assert pending not in feed_ids(response)
        assert feed_ids(client.get(f"{HOSTEL_FEED}?hostel_id={world['new'].id}", headers=headers)) == {new_item}
        missing = client.get(f"{HOSTEL_FEED}?hostel_id=999999", headers=headers)
        assert missing.status_code == 404 and missing.json()["detail"]["code"] == "hostel_not_found"

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

def test_hostel_specific_it_complaint_stays_hmc_restricted_but_keeps_its_it_workflow(
    client, world, student_headers, student_b_headers, seeded_departments,
):
    it = seeded_departments["it"].id
    created = submit(client, student_headers, it, "Wing A Wi-Fi access point dead",
                     floor_id=world["floors"]["A1"].id).json()
    cid = created["id"]
    assert created["department_id"] == it
    assert created["visibility_scope"] == "hmc_group_public"
    assert created["publication_status"] == "published"

    assert cid not in feed_ids(client.get(dept_feed(it), headers=student_b_headers))
    assert cid in feed_ids(client.get(HOSTEL_FEED, headers=student_headers))
    assert cid not in feed_ids(client.get(HOSTEL_FEED, headers=student_b_headers))
    assert client.get(f"/api/v1/feeds/items/{cid}", headers=student_b_headers).status_code == 404

    # IT staff still handle it through the normal department queue.
    it_headers = headers_for(world["it_staff"])
    assert cid in {i["id"] for i in client.get("/api/v1/staff/complaints", headers=it_headers).json()}
    moved = client.patch(f"/api/v1/staff/complaints/{cid}/status", headers=it_headers,
                         json={"status": "in_progress", "remark": "Technician assigned."})
    assert moved.status_code == 200, moved.text
    # ...but the IT queue does not grant HMC feed access or item visibility.
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


def test_duplicate_candidates_follow_publication_and_group_rules(
    client, db, world, student_user, student_b_user, student_headers, student_b_headers, admin_headers,
    seeded_departments,
):
    it, hostel = seeded_departments["it"].id, seeded_departments["hostel"].id
    floors = world["floors"]
    title = "Corridor router offline"
    ids = {
        "alice_own_private": submit(client, student_headers, it, title, is_public=False, description=DUP_TEXT),
        "bob_private": submit(client, student_b_headers, it, title, is_public=False, description=DUP_TEXT),
        "bob_department_public": submit(client, student_b_headers, it, title, description=DUP_TEXT),
        "bob_own_group": submit(client, student_b_headers, hostel, title, description=DUP_TEXT, floor_id=floors["C1"].id),
        "bob_pending_in_ab1": submit(client, student_b_headers, hostel, title, description=DUP_TEXT, floor_id=floors["B1"].id),
        "bob_rejected_in_ab1": submit(client, student_b_headers, hostel, title, description=DUP_TEXT, floor_id=floors["A1"].id),
        "bob_unmapped": submit(client, student_b_headers, hostel, title, description=DUP_TEXT, floor_id=floors["D1"].id),
        "bob_legacy_text": submit(client, student_b_headers, it, title, description=DUP_TEXT, hostel="Main Hostel"),
    }
    ids = {key: response.json()["id"] for key, response in ids.items()}
    client.post(decision(ids["bob_rejected_in_ab1"]), headers=admin_headers,
                json={"decision": "rejected", "note": "Not substantiated."})

    alice_matches = duplicate_ids(client, student_headers, title, DUP_TEXT)
    assert alice_matches <= {ids["alice_own_private"], ids["bob_department_public"]}
    assert ids["alice_own_private"] in alice_matches
    assert ids["bob_department_public"] in alice_matches

    # Approving the pending AB1 report makes it a candidate for AB1 members only.
    client.post(decision(ids["bob_pending_in_ab1"]), headers=admin_headers, json={"decision": "approved"})
    matches = client.post("/api/v1/complaints/duplicate-suggestions", headers=student_headers,
                          json={"title": title, "description": DUP_TEXT}).json()["matches"]
    from app.services.duplicate_service import visible_duplicate_candidates
    visible = {c.id for c in visible_duplicate_candidates(db, student_user)}
    assert visible == {ids["alice_own_private"], ids["bob_department_public"], ids["bob_pending_in_ab1"]}
    assert {m["id"] for m in matches} == visible
    bob_visible = {c.id for c in visible_duplicate_candidates(db, student_b_user)}
    assert ids["bob_own_group"] in bob_visible and ids["alice_own_private"] not in bob_visible
    for match in matches:
        assert set(match) == {"id", "title", "department_id", "department_name", "status", "similarity_score"}


def test_duplicate_threshold_and_algorithm_are_preserved(client, world, student_headers):
    response = client.post("/api/v1/complaints/duplicate-suggestions", headers=student_headers,
                           json={"title": "Anything at all", "description": "Some description text here."})
    assert response.status_code == 200
    assert response.json()["threshold"] == 0.70


def test_same_group_members_receive_duplicate_suggestions(
    client, db, world, student_b_user, student_headers, student_b_headers, seeded_departments,
):
    set_residence(db, student_b_user, world["floors"]["B1"], world["hostel_staff"])
    created = submit(client, student_headers, seeded_departments["it"].id, "Wing A router outage",
                     floor_id=world["floors"]["A1"].id)
    assert created.json()["publication_status"] == "published"
    assert created.json()["id"] in duplicate_ids(client, student_b_headers, "Wing A router outage",
                                                 "A detailed report describing the observed campus issue.")


def test_duplicate_suggestions_do_not_leak_published_items_across_groups(
    client, world, student_headers, student_b_headers, seeded_departments,
):
    created = submit(client, student_headers, seeded_departments["it"].id, "Wing A router offline",
                     floor_id=world["floors"]["A1"].id)
    assert created.json()["publication_status"] == "published"
    assert created.json()["id"] not in duplicate_ids(
        client, student_b_headers, "Wing A router offline",
        "The Wing A router is offline and campus network connectivity is disrupted.",
    )
