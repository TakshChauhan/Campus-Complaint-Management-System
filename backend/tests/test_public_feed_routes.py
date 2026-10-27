"""Regression tests for verified residence, publication state, moderation and feed privacy."""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.building import Building
from app.models.complaint import Complaint
from app.models.complaint_publication_audit import ComplaintPublicationAudit
from app.models.floor import Floor
from app.models.hmc_group import HMCGroup, HMCGroupWing
from app.models.hmc_group_moderator import HMCGroupModerator
from app.models.user import User
from app.models.wing import Wing
from app.schemas.public_feed import FeedReviewRequest
from app.services.public_feed_service import (
    _student_hmc_group, assign_hmc_moderator, list_hmc_publication_review_queue,
    review_hmc_publication, verify_student_residence,
)


def _admin(db):
    admin = (
        db.query(User)
        .filter(
            User.role == "admin",
            User.is_active.is_(True),
        )
        .first()
    )

    if admin is None:
        admin = User(
            name="Public Feed Test Admin",
            email="public-feed-test-admin@campus.edu",
            password_hash=None,
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

    return admin


def _verify(db, admin, student, building, floor, wing):
    student.residence_building_id = building.id
    student.residence_floor_id = floor.id
    student.wing_id = wing.id
    student.residence_verified_at = datetime.now(timezone.utc)
    student.residence_verified_by_id = admin.id


def _create_hmc_map(db, *, student_user, student_b_user):
    admin = _admin(db)
    building = Building(name="Main Hostel")
    db.add(building); db.flush()
    floor1 = Floor(name="1", building_id=building.id)
    floor2 = Floor(name="2", building_id=building.id)
    floor3 = Floor(name="3", building_id=building.id)
    db.add_all([floor1, floor2, floor3]); db.flush()
    # Wings are building-level entities. The same Wing B can be associated with
    # distinct HMC groups on floors 1, 2, and 3 via HMCGroupWing.
    wing_a = Wing(name="A", building_id=building.id)
    wing_b = Wing(name="B", building_id=building.id)
    wing_c = Wing(name="C", building_id=building.id)
    wing_d = Wing(name="D", building_id=building.id)
    db.add_all([wing_a, wing_b, wing_c, wing_d]); db.flush()
    group_ab = HMCGroup(name="Floor 1 HMC AB", building_id=building.id, floor_id=floor1.id)
    group_c = HMCGroup(name="Floor 1 HMC C", building_id=building.id, floor_id=floor1.id)
    group_d = HMCGroup(name="Floor 2 HMC BD", building_id=building.id, floor_id=floor2.id)
    group_bc3 = HMCGroup(name="Floor 3 HMC BC", building_id=building.id, floor_id=floor3.id)
    db.add_all([group_ab, group_c, group_d, group_bc3]); db.flush()
    db.add_all([
        HMCGroupWing(hmc_group_id=group_ab.id, building_id=building.id, floor_id=floor1.id, wing_id=wing_a.id),
        HMCGroupWing(hmc_group_id=group_ab.id, building_id=building.id, floor_id=floor1.id, wing_id=wing_b.id),
        HMCGroupWing(hmc_group_id=group_c.id, building_id=building.id, floor_id=floor1.id, wing_id=wing_c.id),
        HMCGroupWing(hmc_group_id=group_d.id, building_id=building.id, floor_id=floor2.id, wing_id=wing_b.id),
        HMCGroupWing(hmc_group_id=group_d.id, building_id=building.id, floor_id=floor2.id, wing_id=wing_d.id),
        HMCGroupWing(hmc_group_id=group_bc3.id, building_id=building.id, floor_id=floor3.id, wing_id=wing_b.id),
        HMCGroupWing(hmc_group_id=group_bc3.id, building_id=building.id, floor_id=floor3.id, wing_id=wing_c.id),
    ])
    _verify(db, admin, student_user, building, floor1, wing_a)
    _verify(db, admin, student_b_user, building, floor1, wing_c)
    db.commit()
    return {"building": building, "floor1": floor1, "floor2": floor2, "floor3": floor3,
            "wing_a": wing_a, "wing_b": wing_b, "wing_c": wing_c, "wing_d": wing_d,
            "group_ab": group_ab, "group_c": group_c, "group_d": group_d, "group_bc3": group_bc3}


def _submit(client, headers, department_id, title, **location):
    return client.post("/api/v1/complaints", json={
        "title": title, "description": "A detailed report describing the observed campus issue.",
        "department_id": department_id, "is_public": True, **location,
    }, headers=headers)


def _wing_location(mapping, key, floor_key="floor1"):
    return {"affected_building_id": mapping["building"].id,
            "affected_floor_id": mapping[floor_key].id,
            "affected_wing_id": mapping[key].id}


def test_department_feed_excludes_hmc_and_never_returns_description_or_reporter_identity(
    client, db, student_user, student_b_user, student_headers, seeded_departments
):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    dep = seeded_departments["it"].id
    department_public = _submit(client, student_headers, dep, "Campus Wi-Fi outage")
    hmc = _submit(client, student_headers, dep, "Wing C access point broken", **_wing_location(loc, "wing_c"))
    assert department_public.status_code == 201, department_public.text
    assert department_public.json()["publication_status"] == "published"
    assert hmc.status_code == 201, hmc.text
    assert hmc.json()["publication_status"] == "pending_review"
    response = client.get(f"/api/v1/complaints/feed?department_id={dep}", headers=student_headers)
    assert response.status_code == 200
    values = response.json()
    ids = {item["id"] for item in values}
    assert department_public.json()["id"] in ids
    assert hmc.json()["id"] not in ids
    item = next(item for item in values if item["id"] == department_public.json()["id"])
    assert not ({"description", "description_preview", "created_by_id", "reporter_id", "reporter_name", "reporter_email", "email", "name"} & set(item))
    assert item["title"] == "Campus Wi-Fi outage"


def test_hostel_department_feed_is_rejected_for_every_authenticated_role(
    client, seeded_departments, student_headers, staff_headers, admin_headers,
):
    hostel_id = seeded_departments["hostel"].id
    for headers in (student_headers, staff_headers, admin_headers):
        response = client.get(f"/api/v1/complaints/feed?department_id={hostel_id}", headers=headers)
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "hostel_feed_required"


def test_department_feed_is_accessible_to_authenticated_students_staff_and_admins(
    client, seeded_departments, student_headers, staff_headers, admin_headers,
):
    department_id = seeded_departments["it"].id
    created = _submit(client, student_headers, department_id, "Campus public Wi-Fi issue")
    assert created.status_code == 201, created.text
    for headers in (student_headers, staff_headers, admin_headers):
        response = client.get(f"/api/v1/complaints/feed?department_id={department_id}", headers=headers)
        assert response.status_code == 200
        assert str(response.headers["X-Total-Count"]) == "1"
        assert created.json()["id"] in {item["id"] for item in response.json()}


def test_unlocated_public_hostel_complaint_never_leaks_via_detail_or_duplicates(
    client, db, seeded_departments, student_headers, student_b_headers,
):
    hostel_id = seeded_departments["hostel"].id
    created = _submit(client, student_headers, hostel_id, "Unlocated hostel Wi-Fi outage")
    assert created.status_code == 201, created.text
    assert created.json()["publication_status"] == "pending_mapping"
    complaint_id = created.json()["id"]
    detail = client.get(f"/api/v1/complaints/feed/items/{complaint_id}", headers=student_b_headers)
    assert detail.status_code == 404

    # Also protect against old/misclassified records that have no location.
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).one()
    complaint.visibility_scope = "department_public"
    complaint.feed_review_status = "not_required"
    complaint.publication_status = "published"
    db.commit()
    detail = client.get(f"/api/v1/complaints/feed/items/{complaint_id}", headers=student_b_headers)
    assert detail.status_code == 404
    suggestions = client.post("/api/v1/complaints/duplicate-suggestions", json={
        "title": "Unlocated hostel Wi-Fi outage",
        "description": "A detailed report describing the observed campus issue.",
    }, headers=student_b_headers)
    assert suggestions.status_code == 200, suggestions.text
    assert complaint_id not in {item["id"] for item in suggestions.json()["matches"]}


def test_unverified_residence_cannot_auto_publish_even_when_student_selects_own_wing(
    client, db, student_user, student_b_user, student_headers, seeded_departments
):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    student_user.residence_verified_at = None
    student_user.residence_verified_by_id = None
    db.commit()
    complaint = _submit(client, student_headers, seeded_departments["hostel"].id,
        "Unverified Wing A water issue", **_wing_location(loc, "wing_a"))
    assert complaint.status_code == 201
    assert complaint.json()["publication_status"] == "pending_review"
    assert complaint.json()["feed_review_status"] == "pending"


def test_verified_member_may_auto_publish_to_their_responsible_hmc_group(
    client, db, student_user, student_b_user, student_headers, seeded_departments
):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    response = _submit(client, student_headers, seeded_departments["hostel"].id,
        "Wing A light issue", **_wing_location(loc, "wing_a"))
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["publication_status"] == "published"
    assert item["feed_review_status"] == "auto_approved"
    feed = client.get("/api/v1/complaints/feed/hmc", headers=student_headers)
    assert item["id"] in {entry["id"] for entry in feed.json()}


def test_outside_group_report_requires_moderator_review_and_is_location_scoped(
    client, db, student_user, student_b_user, student_headers, student_b_headers,
    admin_headers, seeded_departments
):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    dep = seeded_departments["it"].id
    response = _submit(client, student_headers, dep, "Wing C electrical issue", **_wing_location(loc, "wing_c"))
    assert response.status_code == 201, response.text
    complaint_id = response.json()["id"]
    assert response.json()["publication_status"] == "pending_review"
    before = client.get("/api/v1/complaints/feed/hmc", headers=student_b_headers)
    assert complaint_id not in {item["id"] for item in before.json()}
    queue = client.get("/api/v1/complaints/feed/review-queue", headers=admin_headers)
    assert queue.status_code == 200
    queue_item = next(item for item in queue.json() if item["id"] == complaint_id)
    assert queue_item["reporter_id"] == student_user.id
    approved = client.post(f"/api/v1/complaints/feed/review/{complaint_id}",
                           json={"decision": "approved"}, headers=admin_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["publication_status"] == "published"
    feed_b = client.get("/api/v1/complaints/feed/hmc", headers=student_b_headers)
    feed_a = client.get("/api/v1/complaints/feed/hmc", headers=student_headers)
    assert complaint_id in {item["id"] for item in feed_b.json()}
    assert complaint_id not in {item["id"] for item in feed_a.json()}
    detail = client.get(f"/api/v1/complaints/feed/items/{complaint_id}", headers=student_b_headers)
    assert detail.status_code == 200
    assert "description" not in detail.json() and "description_preview" not in detail.json()
    assert "reporter_id" not in detail.json()


def test_floor_common_area_stays_hidden_until_explicit_audience(
    client, db, student_user, student_b_user, student_headers, student_b_headers, seeded_departments
):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    response = _submit(client, student_headers, seeded_departments["hostel"].id,
        "Floor 1 common water supply", affected_building_id=loc["building"].id,
        affected_floor_id=loc["floor1"].id)
    assert response.status_code == 201, response.text
    assert response.json()["publication_status"] == "pending_mapping"
    cid = response.json()["id"]
    feed_a = client.get("/api/v1/complaints/feed/hmc", headers=student_headers)
    feed_c = client.get("/api/v1/complaints/feed/hmc", headers=student_b_headers)
    assert cid not in {i["id"] for i in feed_a.json()}
    assert cid not in {i["id"] for i in feed_c.json()}


def test_hmc_membership_uses_verified_floor_and_wing_not_wing_alone(
    db, student_user, student_b_user
):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    # Both groups use building-level Wing B, but the assigned floor selects the group.
    verify_student_residence(db, _admin(db), student_b_user.id, building_id=loc["building"].id,
                             floor_id=loc["floor2"].id, wing_id=loc["wing_b"].id)
    group = _student_hmc_group(db, student_b_user)
    assert group.id == loc["group_d"].id
    assert group.floor_id == loc["floor2"].id


def test_unassigned_or_unverified_student_cannot_open_hmc_feed(client, db, student_user,
                                                                 student_b_user, student_b_headers):
    _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    student_b_user.wing_id = None
    student_b_user.residence_building_id = None
    student_b_user.residence_floor_id = None
    student_b_user.residence_verified_at = None
    student_b_user.residence_verified_by_id = None
    db.commit()
    response = client.get("/api/v1/complaints/feed/hmc", headers=student_b_headers)
    assert response.status_code == 403


def test_rejection_requires_reason_and_never_publishes(client, db, student_user, student_b_user,
    student_headers, student_b_headers, admin_headers, seeded_departments):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    response = _submit(client, student_headers, seeded_departments["hostel"].id,
        "Wing C suspicious report", **_wing_location(loc, "wing_c"))
    cid = response.json()["id"]
    no_reason = client.post(f"/api/v1/complaints/feed/review/{cid}", json={"decision": "rejected"}, headers=admin_headers)
    assert no_reason.status_code == 422
    rejected = client.post(f"/api/v1/complaints/feed/review/{cid}",
        json={"decision": "rejected", "note": "Location/details could not be substantiated."}, headers=admin_headers)
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["publication_status"] == "rejected"
    assert db.query(ComplaintPublicationAudit).filter_by(complaint_id=cid, action="rejected").count() == 1
    feed = client.get("/api/v1/complaints/feed/hmc", headers=student_b_headers)
    assert cid not in {i["id"] for i in feed.json()}


def test_student_cannot_read_review_queue_or_approve(client, db, student_user, student_b_user,
    student_headers, seeded_departments):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    response = client.get("/api/v1/complaints/feed/review-queue", headers=student_headers)
    assert response.status_code == 403
    complaint = _submit(client, student_headers, seeded_departments["it"].id,
        "Outside wing report", **_wing_location(loc, "wing_c"))
    result = client.post(f"/api/v1/complaints/feed/review/{complaint.json()['id']}",
        json={"decision": "approved"}, headers=student_headers)
    assert result.status_code == 403


def test_unknown_or_inconsistent_location_creates_pending_mapping_not_publication(
    client, db, student_user, student_b_user, student_headers, seeded_departments
):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    other = Building(name="Other Hostel"); db.add(other); db.commit(); db.refresh(other)
    response = _submit(client, student_headers, seeded_departments["hostel"].id,
        "Unknown building wing issue", affected_building_id=other.id,
        affected_floor_id=loc["floor1"].id, affected_wing_id=loc["wing_a"].id)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["publication_status"] == "pending_mapping"
    assert data["affected_building_id"] is None
    # Hostel department feeds must be rejected; unresolved complaints also stay
    # hidden from the restricted HMC feed.
    department_feed = client.get(
        f"/api/v1/complaints/feed?department_id={seeded_departments['hostel'].id}",
        headers=student_headers,
    )
    assert department_feed.status_code == 400
    assert department_feed.json()["detail"]["code"] == "hostel_feed_required"
    hmc_feed = client.get("/api/v1/complaints/feed/hmc", headers=student_headers)
    assert hmc_feed.status_code == 200
    assert data["id"] not in {item["id"] for item in hmc_feed.json()}


def test_configured_location_without_an_hmc_group_stays_pending_mapping(
    client, db, student_user, student_b_user, student_headers, seeded_departments
):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    # Wing D is a real configured building-level wing but is not mapped on floor 3.
    response = _submit(client, student_headers, seeded_departments["hostel"].id,
        "Wing D floor 3 ventilation", affected_building_id=loc["building"].id,
        affected_floor_id=loc["floor3"].id, affected_wing_id=loc["wing_d"].id)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["publication_status"] == "pending_mapping"
    assert data["feed_review_status"] == "pending"
    feed = client.get("/api/v1/complaints/feed/hmc", headers=student_headers)
    assert data["id"] not in {item["id"] for item in feed.json()}


def test_duplicate_suggestions_do_not_leak_published_hmc_items_across_groups(
    client, db, student_user, student_b_user, student_headers, student_b_headers, seeded_departments
):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    created = _submit(client, student_headers, seeded_departments["it"].id,
        "Wing A router offline", **_wing_location(loc, "wing_a"))
    assert created.status_code == 201, created.text
    assert created.json()["publication_status"] == "published"
    suggestions = client.post("/api/v1/complaints/duplicate-suggestions", headers=student_b_headers, json={
        "title": "Wing A router offline",
        "description": "The Wing A router is offline and campus network connectivity is disrupted.",
    })
    assert suggestions.status_code == 200, suggestions.text
    assert created.json()["id"] not in {item.get("id") for item in suggestions.json().get("matches", [])}


def test_same_hmc_group_members_can_receive_duplicate_suggestions(
    client, db, student_user, student_b_user, student_headers, student_b_headers,
    seeded_departments,
):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    verify_student_residence(db, _admin(db), student_b_user.id,
                             building_id=loc["building"].id,
                             floor_id=loc["floor1"].id, wing_id=loc["wing_b"].id)
    created = _submit(client, student_headers, seeded_departments["it"].id,
                      "Wing A router outage", **_wing_location(loc, "wing_a"))
    assert created.status_code == 201, created.text
    assert created.json()["publication_status"] == "published"
    response = client.post("/api/v1/complaints/duplicate-suggestions",
        headers=student_b_headers,
        json={"title": "Wing A router outage",
              "description": "A detailed report describing the observed campus issue."})
    assert response.status_code == 200, response.text
    assert created.json()["id"] in {item["id"] for item in response.json()["matches"]}


def test_unknown_legacy_building_location_remains_pending_mapping(client, db, student_user,
    student_b_user, student_headers, seeded_departments):
    _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    response = _submit(client, student_headers, seeded_departments["hostel"].id,
        "Legacy location complaint", hostel="Unlisted Building", floor="2", wing="B")
    assert response.status_code == 201, response.text
    assert response.json()["publication_status"] == "pending_mapping"
    assert response.json()["hostel"] == "Unlisted Building"


def test_location_catalogue_contains_buildings_and_only_mapped_active_locations(
    client, db, student_user, student_b_user, student_headers):
    _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    response = client.get("/api/v1/complaints/feed/locations", headers=student_headers)
    assert response.status_code == 200
    data = response.json()
    assert {item["name"] for item in data["buildings"]} == {"Main Hostel"}
    assert {item["name"] for item in data["floors"]} == {"1", "2", "3"}
    assert {item["name"] for item in data["wings"]} == {"A", "B", "C", "D"}
    assert not (set(data) & {"hmc_group_ids", "student_assignments"})


def test_pending_hmc_complaints_are_not_leaked_via_duplicate_suggestions(
    client, db, student_user, student_b_user, student_headers, student_b_headers, seeded_departments):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    response = _submit(client, student_headers, seeded_departments["it"].id,
        "Wing C router failed", **_wing_location(loc, "wing_c"))
    cid = response.json()["id"]
    suggestions = client.post("/api/v1/complaints/duplicate-suggestions",
        json={"title": "Wing C router failed", "description": "A detailed report of the router failing repeatedly."},
        headers=student_b_headers)
    assert suggestions.status_code == 200
    assert cid not in {item.get("id") for item in suggestions.json().get("matches", [])}


def test_corrupt_hmc_group_with_more_than_two_wings_fails_closed(client, db, student_user,
    student_b_user, student_headers):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    extra = Wing(name="E", building_id=loc["building"].id); db.add(extra); db.flush()
    db.add(HMCGroupWing(hmc_group_id=loc["group_ab"].id, building_id=loc["building"].id,
        floor_id=loc["floor1"].id, wing_id=extra.id)); db.commit()
    response = client.get("/api/v1/complaints/feed/hmc", headers=student_headers)
    assert response.status_code == 403


def test_private_location_complaint_never_enters_feeds(client, db, student_user, student_b_user,
    student_headers, seeded_departments):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    response = client.post("/api/v1/complaints", headers=student_headers, json={
        "title": "Private Wing B concern", "description": "An issue for the assigned department only.",
        "department_id": seeded_departments["it"].id, "is_public": False,
        **_wing_location(loc, "wing_b"),
    })
    assert response.status_code == 201
    data = response.json()
    assert data["publication_status"] == "private"
    assert data["visibility_scope"] == "private"
    dep = client.get(f"/api/v1/complaints/feed?department_id={seeded_departments['it'].id}", headers=student_headers)
    hmc = client.get("/api/v1/complaints/feed/hmc", headers=student_headers)
    assert data["id"] not in {i["id"] for i in dep.json()}
    assert data["id"] not in {i["id"] for i in hmc.json()}


def test_arbitrary_department_staff_cannot_moderate_but_designated_hmc_moderator_can(
    db, student_user, student_b_user, seeded_departments):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    admin = _admin(db)
    staff = db.query(User).filter(User.role == "staff", User.is_active.is_(True)).first()
    if staff is None:
        staff = User(name="HMC Test Staff", email="hmc-test-staff@example.edu", role="staff",
                     department_id=seeded_departments["it"].id, is_active=True, email_verified=True)
        db.add(staff); db.commit(); db.refresh(staff)
    with pytest.raises(HTTPException) as err:
        list_hmc_publication_review_queue(db, staff)
    assert err.value.status_code == 403
    assign_hmc_moderator(db, admin, loc["group_ab"].id, staff.id, assigned=True)
    _, count = list_hmc_publication_review_queue(db, staff)
    assert count >= 0
    assert db.query(HMCGroupModerator).filter_by(hmc_group_id=loc["group_ab"].id, user_id=staff.id).count() == 1


def test_unpublish_records_audit_and_removes_item_from_feed(client, db, student_user, student_b_user,
    student_headers, admin_headers, seeded_departments):
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    created = _submit(client, student_headers, seeded_departments["it"].id, "Campus network outage")
    assert created.status_code == 201
    cid = created.json()["id"]
    before = client.get(f"/api/v1/complaints/feed?department_id={seeded_departments['it'].id}", headers=student_headers)
    assert cid in {item["id"] for item in before.json()}
    result = client.post(f"/api/v1/complaints/feed/unpublish/{cid}",
        json={"note": "Contains inappropriate public-facing content."}, headers=admin_headers)
    assert result.status_code == 200, result.text
    assert result.json()["publication_status"] == "rejected"
    assert db.query(ComplaintPublicationAudit).filter_by(complaint_id=cid, action="unpublished").count() == 1
    after = client.get(f"/api/v1/complaints/feed?department_id={seeded_departments['it'].id}", headers=student_headers)
    assert cid not in {item["id"] for item in after.json()}


def test_shared_floor_requires_explicit_audience_and_never_leaks_to_other_groups(
    client, db, student_user, student_b_user, student_headers, student_b_headers,
    admin_headers, seeded_departments,
):
    """A wing-less/shared-floor complaint stays hidden until an admin selects groups."""
    loc = _create_hmc_map(db, student_user=student_user, student_b_user=student_b_user)
    created = _submit(
        client, student_headers, seeded_departments["it"].id,
        "Shared floor water leak", affected_building_id=loc["building"].id,
        affected_floor_id=loc["floor1"].id,
    )
    assert created.status_code == 201, created.text
    complaint_id = created.json()["id"]
    assert created.json()["publication_status"] == "pending_mapping"

    for headers in (student_headers, student_b_headers):
        feed = client.get("/api/v1/complaints/feed/hmc", headers=headers)
        assert feed.status_code == 200, feed.text
        assert complaint_id not in {item["id"] for item in feed.json()}

    missing_audience = client.post(
        f"/api/v1/complaints/feed/review/{complaint_id}",
        json={"decision": "approved"}, headers=admin_headers,
    )
    assert missing_audience.status_code == 422, missing_audience.text

    approved = client.post(
        f"/api/v1/complaints/feed/review/{complaint_id}",
        json={"decision": "approved", "audience_group_ids": [loc["group_ab"].id]},
        headers=admin_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["publication_status"] == "published"

    group_ab_feed = client.get("/api/v1/complaints/feed/hmc", headers=student_headers)
    group_c_feed = client.get("/api/v1/complaints/feed/hmc", headers=student_b_headers)
    assert complaint_id in {item["id"] for item in group_ab_feed.json()}
    assert complaint_id not in {item["id"] for item in group_c_feed.json()}

    group_ab_detail = client.get(
        f"/api/v1/complaints/feed/items/{complaint_id}", headers=student_headers,
    )
    group_c_detail = client.get(
        f"/api/v1/complaints/feed/items/{complaint_id}", headers=student_b_headers,
    )
    assert group_ab_detail.status_code == 200
    assert group_c_detail.status_code == 404

    duplicate = client.post(
        "/api/v1/complaints/duplicate-suggestions", headers=student_b_headers,
        json={"title": "Shared floor water leak", "description": "A water leak is affecting the shared floor area."},
    )
    assert duplicate.status_code == 200, duplicate.text
    assert complaint_id not in {item["id"] for item in duplicate.json()["matches"]}
