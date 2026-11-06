"""S3-33: privacy tests for student residences and cross-hostel duplicate suggestions.

Two things in Sprint 3 can leak personal or location data if they are wrong:

A. Residences  (API contract 7.3-7.5, section 8)
   A residence says where a student sleeps and decides which complaints they can
   read. Only the student and authorized Hostel staff/admins may see it; nobody
   can set, verify or widen it for themselves; and it must never surface in a
   feed, a duplicate suggestion or an error message.

B. Cross-hostel duplicates  (API contract 6.4, 7.10, section 8)
   Duplicate suggestions compare free text, so they are the easiest side channel
   to read another hostel's complaints. A student may be matched only against
   their own complaints, published department-wide complaints and published
   complaints located in their own verified hostel (Model 2, S4-09). The two
   hostels in the shared world both have a "floor 1", which is exactly the kind
   of collision a careless floor-level check would get wrong.

Every "nothing leaks" test has a positive control next to it (the same student
DOES get the item they are entitled to), so a test cannot pass just because
nothing is returned at all.

Run just this file:   pytest tests/test_sprint3_privacy.py -v
"""
import pytest

from app.core.config import settings
from app.models.complaint_hmc_audience import ComplaintHMCAudience
from app.models.student_residence import StudentResidence
from sprint3_hmc_world import build_world, headers_for, make_user, set_residence, submit

MY_RESIDENCE = "/api/v1/users/me/residence"
RESIDENCE_QUEUE = "/api/v1/staff/residences"
HOSTEL_FEED = "/api/v1/feeds/hostel"
MOD_QUEUE = "/api/v1/hmc/publication-requests"
DUPLICATES = "/api/v1/complaints/duplicate-suggestions"
MATCH_KEYS = {"id", "title", "department_id", "department_name", "status", "similarity_score"}

LEAK_MARKER = "PRIVATE-DETAIL"
DUP_TITLE = "Corridor router offline"
DUP_TEXT = f"{LEAK_MARKER} The corridor router is offline and the network connectivity is disrupted all day."


def decide(residence_id: int) -> str:
    return f"{RESIDENCE_QUEUE}/{residence_id}/decision"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    monkeypatch.setattr("sprint3_hmc_world.get_password_hash", lambda _password: "not-a-real-hash")


@pytest.fixture
def departments(db):
    from app.models.department import Department
    rows = {
        "it": Department(name="IT Services", description="IT", is_active=True),
        "hostel": Department(name="Hostel", description="Hostel", is_active=True),
    }
    db.add_all(rows.values())
    db.commit()
    return rows


@pytest.fixture
def world(db, departments):
    alice = make_user(db, "alice", "student")  # Main Hostel A1
    bob = make_user(db, "bob", "student")  # Main Hostel C1
    return build_world(db, departments, alice, bob) | {"alice": alice, "bob": bob}


@pytest.fixture
def people(db, world):
    """Named users. carol lives in Alice's hostel (B1); nh lives in the other hostel; eve starts pending."""
    floors, staff = world["floors"], world["hostel_staff"]
    carol = make_user(db, "carol", "student")
    set_residence(db, carol, floors["B1"], staff)
    nh = make_user(db, "nh.resident", "student")
    set_residence(db, nh, floors["N1"], staff)
    eve = make_user(db, "eve", "student")
    set_residence(db, eve, floors["A1"], None, status="pending")
    return {
        "alice": world["alice"], "bob": world["bob"], "carol": carol, "nh": nh, "eve": eve,
        "hostel_staff": staff, "it_staff": world["it_staff"],
        "admin": make_user(db, "chief.admin", "admin"),
        "other_staff": make_user(db, "nodept.staff", "staff"),
    }


@pytest.fixture
def hdr(people):
    return {key: headers_for(user) for key, user in people.items()}


def post_complaint(client, headers, department_id, title, **extra) -> int:
    response = submit(client, headers, department_id, title, description=DUP_TEXT, **extra)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def suggestions(client, headers, title=DUP_TITLE, description=DUP_TEXT):
    response = client.post(DUPLICATES, headers=headers, json={"title": title, "description": description})
    assert response.status_code == 200, response.text
    return response


def match_ids(client, headers, **kwargs) -> set[int]:
    return {match["id"] for match in suggestions(client, headers, **kwargs).json()["matches"]}


# =========================================================================== #
# A. RESIDENCES
# =========================================================================== #

def test_my_residence_returns_only_the_callers_own_record_without_any_identity(client, world, hdr):
    alice = client.get(MY_RESIDENCE, headers=hdr["alice"])
    bob = client.get(MY_RESIDENCE, headers=hdr["bob"])
    assert alice.json() == {"floor_id": world["floors"]["A1"].id, "hostel": "Main Hostel", "wing": "Wing A",
                            "floor": "Floor 1", "status": "verified", "remark": None}
    assert bob.json()["wing"] == "Wing C"
    for response in (alice, bob):
        assert set(response.json()) == {"floor_id", "hostel", "wing", "floor", "status", "remark"}
        for leak in ("@campus.edu", "student_id", "verified_by", "Hostel Staff", "Alice", "Bob", "hmc", "HMC"):
            assert leak not in response.text, leak


def test_residence_routes_take_no_student_identifier_so_other_students_records_are_unreachable(
    client, db, world, people, hdr,
):
    alice_id = people["alice"].id
    for method in ("get", "patch"):
        response = getattr(client, method)(f"/api/v1/users/{alice_id}/residence", headers=hdr["bob"],
                                           **({"json": {"floor_id": world["floors"]["C1"].id}} if method == "patch" else {}))
        assert response.status_code in (404, 405)
    # Naming another student in the body is a validation error, not an impersonation.
    for extra in ({"student_id": alice_id}, {"user_id": alice_id}, {"email": "alice@campus.edu"}):
        response = client.patch(MY_RESIDENCE, headers=hdr["bob"], json={"floor_id": world["floors"]["C1"].id, **extra})
        assert response.status_code == 422
    db.expire_all()
    assert db.query(StudentResidence).filter_by(student_id=alice_id).one().floor_id == world["floors"]["A1"].id


@pytest.mark.parametrize("extra", [
    {"status": "verified"}, {"verified_by_id": 1}, {"verified_at": "2026-01-01T00:00:00Z"},
    {"hmc_group_id": 1}, {"remark": "approved"},
])
def test_students_cannot_smuggle_verification_fields_into_a_residence_update(client, db, world, people, hdr, extra):
    response = client.patch(MY_RESIDENCE, headers=hdr["eve"], json={"floor_id": world["floors"]["A1"].id, **extra})
    assert response.status_code == 422
    db.expire_all()
    stored = db.query(StudentResidence).filter_by(student_id=people["eve"].id).one()
    assert (stored.status, stored.verified_by_id, stored.verified_at) == ("pending", None, None)
    assert client.get(HOSTEL_FEED, headers=hdr["eve"]).status_code == 403


def test_a_student_cannot_verify_their_own_or_anyone_elses_residence(client, db, world, people, hdr):
    residence_id = db.query(StudentResidence).filter_by(student_id=people["eve"].id).one().id
    for who in ("eve", "alice", "carol"):  # the owner, a verified resident, a neighbour
        response = client.post(decide(residence_id), headers=hdr[who], json={"decision": "approve"})
        assert response.status_code == 403, who
    db.expire_all()
    assert db.query(StudentResidence).filter_by(id=residence_id).one().status == "pending"
    assert client.get(HOSTEL_FEED, headers=hdr["eve"]).status_code == 403
    # Control: Hostel staff can, which proves the 403s above are about the caller, not the request.
    assert client.post(decide(residence_id), headers=hdr["hostel_staff"], json={"decision": "approve"}).status_code == 200
    assert client.get(HOSTEL_FEED, headers=hdr["eve"]).status_code == 200


@pytest.mark.parametrize("status", ["pending", "verified", "rejected"])
@pytest.mark.parametrize("viewer", ["alice", "eve", "it_staff", "other_staff"])
def test_residence_queue_with_student_names_and_emails_is_closed_to_everyone_but_hostel_staff_and_admin(
    client, hdr, viewer, status,
):
    response = client.get(f"{RESIDENCE_QUEUE}?status={status}", headers=hdr[viewer])
    assert response.status_code == 403
    assert "@campus.edu" not in response.text and "student_email" not in response.text


def test_residence_queue_shows_identity_to_hostel_staff_and_admin_and_nobody_else(client, hdr):
    for viewer in ("hostel_staff", "admin"):
        response = client.get(f"{RESIDENCE_QUEUE}?status=verified", headers=hdr[viewer])
        assert response.status_code == 200
        emails = {item["student_email"] for item in response.json()}
        assert {"alice@campus.edu", "bob@campus.edu", "carol@campus.edu", "nh.resident@campus.edu"} <= emails
    assert client.get(RESIDENCE_QUEUE).status_code == 401


def test_a_rejection_remark_reaches_only_its_student_and_authorized_staff(
    client, db, world, people, hdr, departments,
):
    remark = "REMARK-FOR-EVE-ONLY: room allotment list shows a different floor."
    residence_id = db.query(StudentResidence).filter_by(student_id=people["eve"].id).one().id
    rejected = client.post(decide(residence_id), headers=hdr["hostel_staff"],
                           json={"decision": "reject", "remark": remark})
    assert rejected.status_code == 200

    # Where it MAY appear.
    assert client.get(MY_RESIDENCE, headers=hdr["eve"]).json()["remark"] == remark
    assert remark in client.get(f"{RESIDENCE_QUEUE}?status=rejected", headers=hdr["admin"]).text

    # Where it must NOT appear: every other reader and every other surface.
    post_complaint(client, hdr["alice"], departments["hostel"].id, "Wing A corridor lamp",
                   floor_id=world["floors"]["A1"].id)
    surfaces = []
    for viewer in ("alice", "bob", "carol", "nh", "hostel_staff", "admin", "it_staff"):
        surfaces += [
            client.get(HOSTEL_FEED, headers=hdr[viewer]),
            client.get("/api/v1/users/me", headers=hdr[viewer]),
        ]
    for viewer in ("alice", "bob", "carol", "nh"):
        surfaces += [client.get(MY_RESIDENCE, headers=hdr[viewer]), suggestions(client, hdr[viewer])]
    for viewer in ("alice", "it_staff", "other_staff"):
        surfaces.append(client.get(RESIDENCE_QUEUE, headers=hdr[viewer]))
    assert all(remark not in response.text for response in surfaces)
    # Eve's own feed explains nothing beyond "not verified".
    denied = client.get(HOSTEL_FEED, headers=hdr["eve"])
    assert denied.status_code == 403 and remark not in denied.text


def test_changing_a_residence_discards_the_old_decision_everywhere(client, db, world, people, hdr):
    residence_id = db.query(StudentResidence).filter_by(student_id=people["alice"].id).one().id
    assert client.get(HOSTEL_FEED, headers=hdr["alice"]).status_code == 200
    moved = client.patch(MY_RESIDENCE, headers=hdr["alice"], json={"floor_id": world["floors"]["N1"].id})
    assert moved.status_code == 200 and moved.json()["status"] == "pending"
    assert moved.json()["hostel"] == "New Hostel"
    db.expire_all()
    stored = db.query(StudentResidence).filter_by(id=residence_id).one()
    assert (stored.verified_by_id, stored.verified_at, stored.remark) == (None, None, None)
    assert client.get(HOSTEL_FEED, headers=hdr["alice"]).status_code == 403
    # The old verification cannot be replayed to approve the new floor.
    pending_ids = {item["student_id"] for item in client.get(RESIDENCE_QUEUE, headers=hdr["admin"]).json()}
    assert people["alice"].id in pending_ids


def test_error_responses_never_reveal_groups_hostels_or_other_residents(client, world, people, hdr):
    denied = client.get(HOSTEL_FEED, headers=hdr["eve"])
    forbidden = client.get(f"{HOSTEL_FEED}?hostel_id={world['new'].id}", headers=hdr["eve"])
    for response in (denied, forbidden):
        assert response.status_code == 403
        for leak in ("Main Floor", "New Floor", "HMC AB", "Main Hostel", "New Hostel", "Wing", "@campus.edu"):
            assert leak not in response.text, leak


def test_unknown_and_inactive_floors_are_indistinguishable_when_declaring_a_residence(client, db, world, hdr):
    world["floors"]["C2"].is_active = False
    db.commit()
    inactive = client.patch(MY_RESIDENCE, headers=hdr["eve"], json={"floor_id": world["floors"]["C2"].id})
    unknown = client.patch(MY_RESIDENCE, headers=hdr["eve"], json={"floor_id": 999999})
    assert inactive.status_code == unknown.status_code == 422
    assert inactive.json() == unknown.json()


def test_a_deactivated_verifier_does_not_leave_a_usable_residence(client, db, world, people, hdr, departments):
    """Verified-by an account that is no longer trusted == not verified, in the feed and in duplicates."""
    published = post_complaint(client, hdr["alice"], departments["hostel"].id, "Wing A geyser",
                               floor_id=world["floors"]["A1"].id)
    assert published in {i["id"] for i in client.get(HOSTEL_FEED, headers=hdr["carol"]).json()}
    assert published in match_ids(client, hdr["carol"])
    world["hostel_staff"].is_active = False
    db.commit()
    assert client.get(HOSTEL_FEED, headers=hdr["carol"]).status_code == 403
    assert published not in match_ids(client, hdr["carol"])


def test_reporter_identity_stays_inside_the_moderation_queue(client, db, world, people, hdr, departments):
    """The New Hostel resident reports Wing B: name/email exist only for Hostel staff and admins."""
    pending = post_complaint(client, hdr["nh"], departments["hostel"].id, "Wing B shower leak",
                             floor_id=world["floors"]["B1"].id)

    for viewer in ("alice", "carol", "bob", "nh", "it_staff", "other_staff"):
        assert client.get(MOD_QUEUE, headers=hdr[viewer]).status_code == 403, viewer

    for moderator in ("admin", "hostel_staff"):  # control: the queue is where identity lives
        item = next(i for i in client.get(MOD_QUEUE, headers=hdr[moderator]).json() if i["id"] == pending)
        assert item["reporter_email"] == "nh.resident@campus.edu"

    approved = client.post(f"{MOD_QUEUE}/{pending}/decision", headers=hdr["hostel_staff"], json={"decision": "approved"})
    assert approved.status_code == 200
    for viewer in ("alice", "carol", "bob", "hostel_staff", "admin"):
        for response in (client.get(HOSTEL_FEED, headers=hdr[viewer]), client.get(f"/api/v1/feeds/items/{pending}", headers=hdr[viewer])):
            assert response.status_code == 200
            for leak in ("Nh.Resident", "nh.resident@campus.edu", "reporter", "created_by"):
                assert leak not in response.text, f"{viewer} saw {leak!r}"


def test_a_complaint_shows_where_it_happened_never_where_the_reporter_lives(client, world, people, hdr, departments):
    """The New Hostel resident reports a Main Hostel Wing B problem: only the Wing B location is published."""
    complaint = post_complaint(client, hdr["nh"], departments["hostel"].id, "Wing B corridor flooding",
                               floor_id=world["floors"]["B1"].id)
    assert client.post(f"{MOD_QUEUE}/{complaint}/decision", headers=hdr["admin"],
                       json={"decision": "approved"}).status_code == 200
    item = client.get(f"/api/v1/feeds/items/{complaint}", headers=hdr["alice"])
    assert item.status_code == 200
    assert (item.json()["hostel"], item.json()["wing"], item.json()["floor"]) == ("Main Hostel", "Wing B", "Floor 1")
    assert "Wing N" not in item.text and "New Hostel" not in item.text
    # The reporter's own hostel never receives it: visibility follows the location, not the reporter.
    assert complaint not in {i["id"] for i in client.get(HOSTEL_FEED, headers=hdr["nh"]).json()}


# --------------------------------------------------------------------------- #
# Residence x duplicate suggestions
# --------------------------------------------------------------------------- #

def _apply_residence_state(db, world, student, state):
    floors, staff = world["floors"], world["hostel_staff"]
    if state == "verified":
        set_residence(db, student, floors["A1"], staff)
    elif state in ("pending", "rejected"):
        set_residence(db, student, floors["A1"], staff, status=state)
    elif state == "none":
        db.query(StudentResidence).filter_by(student_id=student.id).delete()
    elif state == "floor_without_hmc_group":
        set_residence(db, student, floors["D1"], staff)
    elif state == "other_wing_same_hostel":
        set_residence(db, student, floors["C1"], staff)
    elif state == "other_hostel":
        set_residence(db, student, floors["N1"], staff)
    elif state == "student_verifier":
        set_residence(db, student, floors["A1"], make_user(db, "peer", "student"))
    elif state == "inactive_verifier":
        set_residence(db, student, floors["A1"], staff)
        staff.is_active = False
    db.commit()


@pytest.mark.parametrize("state,sees_hostel_item", [
    ("verified", True), ("floor_without_hmc_group", True), ("other_wing_same_hostel", True),
    ("pending", False), ("rejected", False), ("none", False), ("other_hostel", False),
    ("student_verifier", False), ("inactive_verifier", False),
])
def test_duplicate_suggestions_follow_the_verified_residence_and_nothing_else(
    client, db, world, people, hdr, departments, state, sees_hostel_item,
):
    hostel_item = post_complaint(client, hdr["alice"], departments["hostel"].id, DUP_TITLE, floor_id=world["floors"]["A1"].id)
    department_wide = post_complaint(client, hdr["bob"], departments["it"].id, DUP_TITLE)
    # Control: a verified Main Hostel resident is matched with both.
    assert match_ids(client, hdr["carol"]) == {hostel_item, department_wide}

    _apply_residence_state(db, world, people["eve"], state)
    expected = {hostel_item, department_wide} if sees_hostel_item else {department_wide}
    assert match_ids(client, hdr["eve"]) == expected


def test_moving_to_the_other_hostel_swaps_the_visible_hostel_complaints_only_after_verification(
    client, db, world, people, hdr, departments,
):
    mh = post_complaint(client, hdr["bob"], departments["hostel"].id, DUP_TITLE, floor_id=world["floors"]["C1"].id)
    nh = post_complaint(client, hdr["nh"], departments["hostel"].id, DUP_TITLE, floor_id=world["floors"]["N1"].id)
    own = post_complaint(client, hdr["alice"], departments["hostel"].id, DUP_TITLE, floor_id=world["floors"]["A1"].id)
    wide = post_complaint(client, hdr["bob"], departments["it"].id, DUP_TITLE)
    assert match_ids(client, hdr["alice"]) == {own, wide, mh}

    client.patch(MY_RESIDENCE, headers=hdr["alice"], json={"floor_id": world["floors"]["N1"].id})
    # Pending: no hostel complaints at all; her own complaint and department-wide ones remain.
    assert match_ids(client, hdr["alice"]) == {own, wide}
    residence_id = db.query(StudentResidence).filter_by(student_id=people["alice"].id).one().id
    assert client.post(decide(residence_id), headers=hdr["hostel_staff"], json={"decision": "approve"}).status_code == 200
    assert match_ids(client, hdr["alice"]) == {own, wide, nh}
    assert mh not in match_ids(client, hdr["alice"])


# =========================================================================== #
# B. CROSS-HOSTEL DUPLICATES
# =========================================================================== #

@pytest.fixture
def cross(client, world, people, hdr, departments):
    """Identical-text complaints in both hostels, all published, plus a department-wide one."""
    floors, hostel, it = world["floors"], departments["hostel"].id, departments["it"].id
    ids = {
        "alice_a1": post_complaint(client, hdr["alice"], hostel, DUP_TITLE, floor_id=floors["A1"].id),
        "bob_c1": post_complaint(client, hdr["bob"], hostel, DUP_TITLE, floor_id=floors["C1"].id),
        "nh_n1": post_complaint(client, hdr["nh"], hostel, DUP_TITLE, floor_id=floors["N1"].id),
        "it_wide": post_complaint(client, hdr["bob"], it, DUP_TITLE),
    }
    published = {key: client.get(f"/api/v1/complaints/{value}", headers=hdr[owner]).json()["publication_status"]
                 for key, value, owner in (("alice_a1", ids["alice_a1"], "alice"), ("bob_c1", ids["bob_c1"], "bob"),
                                           ("nh_n1", ids["nh_n1"], "nh"), ("it_wide", ids["it_wide"], "bob"))}
    assert set(published.values()) == {"published"}
    return ids


def test_each_hostel_only_matches_its_own_hostel_plus_department_wide_complaints(client, cross, hdr):
    wide = cross["it_wide"]
    main = {cross["alice_a1"], cross["bob_c1"], wide}
    assert match_ids(client, hdr["alice"]) == main
    assert match_ids(client, hdr["carol"]) == main  # same hostel, not the author
    assert match_ids(client, hdr["bob"]) == main
    assert match_ids(client, hdr["nh"]) == {cross["nh_n1"], wide}


def test_hostel_feeds_and_details_are_equally_closed_across_hostels(client, cross, hdr):
    nonexistent = client.get("/api/v1/feeds/items/999999", headers=hdr["alice"])
    for viewer, foreign in (("alice", "nh_n1"), ("carol", "nh_n1"), ("nh", "alice_a1"), ("nh", "bob_c1")):
        response = client.get(f"/api/v1/feeds/items/{cross[foreign]}", headers=hdr[viewer])
        assert (response.status_code, response.json()) == (nonexistent.status_code, nonexistent.json())
    assert {i["id"] for i in client.get(HOSTEL_FEED, headers=hdr["nh"]).json()} == {cross["nh_n1"]}


def test_same_floor_code_in_two_hostels_does_not_cross_the_boundary_even_with_a_stray_audience_row(
    client, db, world, people, hdr, cross,
):
    """Both hostels have a 'floor 1'. A wrong audience row (bad import, manual edit) must still not leak."""
    groups = world["groups"]
    db.add_all([
        ComplaintHMCAudience(complaint_id=cross["nh_n1"], hmc_group_id=groups["AB1"].id,
                             source="shared_floor", decided_by_id=people["admin"].id, note="stray"),
        ComplaintHMCAudience(complaint_id=cross["alice_a1"], hmc_group_id=groups["N1"].id,
                             source="shared_floor", decided_by_id=people["admin"].id, note="stray"),
        ComplaintHMCAudience(complaint_id=cross["bob_c1"], hmc_group_id=groups["N1"].id,
                             source="shared_floor", decided_by_id=people["admin"].id, note="stray"),
    ])
    db.commit()
    for viewer in ("alice", "carol"):
        assert cross["nh_n1"] not in {i["id"] for i in client.get(HOSTEL_FEED, headers=hdr[viewer]).json()}
        assert client.get(f"/api/v1/feeds/items/{cross['nh_n1']}", headers=hdr[viewer]).status_code == 404
        assert cross["nh_n1"] not in match_ids(client, hdr[viewer])
    nh_feed = {i["id"] for i in client.get(HOSTEL_FEED, headers=hdr["nh"]).json()}
    assert nh_feed == {cross["nh_n1"]}
    for foreign in ("alice_a1", "bob_c1"):
        assert client.get(f"/api/v1/feeds/items/{cross[foreign]}", headers=hdr["nh"]).status_code == 404
        assert cross[foreign] not in match_ids(client, hdr["nh"])


def test_audience_routes_are_gone_so_nothing_can_be_shared_across_hostels(client, db, world, people, hdr, cross):
    groups = world["groups"]
    for target, source in ((groups["AB1"], "nh_n1"), (groups["N1"], "alice_a1")):
        response = client.post(f"/api/v1/hmc/complaints/{cross[source]}/audiences", headers=hdr["admin"],
                               json={"hmc_group_id": target.id, "note": "Please share across hostels."})
        assert response.status_code == 404, response.text
    assert db.query(ComplaintHMCAudience).count() == 0
    assert cross["nh_n1"] not in match_ids(client, hdr["alice"])


def test_residents_of_one_hostel_match_each_other_without_any_sharing_step(client, world, hdr, cross):
    """Positive control for the cross-hostel tests: Model 2 needs no audience decision inside a hostel."""
    assert cross["bob_c1"] in match_ids(client, hdr["alice"])
    assert cross["alice_a1"] in match_ids(client, hdr["bob"])
    assert cross["bob_c1"] not in match_ids(client, hdr["nh"])  # still closed to the other hostel
    assert cross["nh_n1"] not in match_ids(client, hdr["alice"])


def test_hidden_complaints_have_no_influence_on_suggestions_not_even_on_scores(
    client, db, world, people, hdr, departments, cross, monkeypatch,
):
    """No side channel: adding complaints a student may not see leaves the response byte-for-byte unchanged."""
    floors, hostel, it = world["floors"], departments["hostel"].id, departments["it"].id
    before = suggestions(client, hdr["carol"]).json()
    assert {m["id"] for m in before["matches"]} == {cross["alice_a1"], cross["bob_c1"], cross["it_wide"]}

    post_complaint(client, hdr["bob"], it, DUP_TITLE, is_public=False)  # private
    post_complaint(client, hdr["nh"], hostel, DUP_TITLE, floor_id=floors["B1"].id)  # pending review (other hostel)
    rejected = post_complaint(client, hdr["nh"], hostel, DUP_TITLE, floor_id=floors["A1"].id)  # will be rejected
    post_complaint(client, hdr["bob"], it, DUP_TITLE, hostel="Main Hostel")  # legacy text-only location
    post_complaint(client, hdr["nh"], hostel, DUP_TITLE + " again", floor_id=floors["N1"].id)  # other hostel
    monkeypatch.setattr(settings, "HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID", False)
    post_complaint(client, hdr["nh"], hostel, DUP_TITLE)  # legacy unlocated Hostel complaint
    assert client.post(f"{MOD_QUEUE}/{rejected}/decision", headers=hdr["admin"],
                       json={"decision": "rejected", "note": "Not substantiated."}).status_code == 200

    assert suggestions(client, hdr["carol"]).json() == before


def test_suggestions_expose_only_the_documented_fields(client, cross, hdr):
    for viewer in ("alice", "carol", "bob", "nh"):
        response = suggestions(client, hdr[viewer])
        assert response.json()["matches"], viewer
        for match in response.json()["matches"]:
            assert set(match) == MATCH_KEYS
        for leak in (LEAK_MARKER, "@campus.edu", "reporter", "created_by", "floor", "wing", "Wing", "hostel_id",
                     "hmc", "residence", "description"):
            assert leak not in response.text, f"{viewer} leaked {leak!r}"


def test_a_students_own_complaints_follow_them_across_a_residence_change(client, db, world, people, hdr, cross):
    """Own complaints are always matchable; they are not hostel data and need no residence."""
    set_residence(db, people["alice"], world["floors"]["A1"], None, status="rejected")
    assert match_ids(client, hdr["alice"]) == {cross["alice_a1"], cross["it_wide"]}
    db.query(StudentResidence).filter_by(student_id=people["alice"].id).delete()
    db.commit()
    assert match_ids(client, hdr["alice"]) == {cross["alice_a1"], cross["it_wide"]}
    assert match_ids(client, hdr["carol"]) == {cross["alice_a1"], cross["bob_c1"], cross["it_wide"]}  # hostel view unchanged


def test_only_students_can_ask_for_duplicate_suggestions(client, hdr, cross):
    """Staff and admins have the feeds; they must not get a text-search oracle over complaints."""
    body = {"title": DUP_TITLE, "description": DUP_TEXT}
    for viewer in ("hostel_staff", "admin", "it_staff", "other_staff"):
        response = client.post(DUPLICATES, headers=hdr[viewer], json=body)
        assert response.status_code == 403, viewer
        assert "matches" not in response.text
    assert client.post(DUPLICATES, json=body).status_code == 401


def test_duplicate_requests_cannot_name_another_student_or_group(client, hdr, people, world, cross):
    for extra in ({"student_id": people["bob"].id}, {"hmc_group_id": world["groups"]["C1"].id},
                  {"hostel_id": world["main"].id}, {"floor_id": world["floors"]["C1"].id}):
        response = client.post(DUPLICATES, headers=hdr["alice"],
                               json={"title": DUP_TITLE, "description": DUP_TEXT, **extra})
        assert response.status_code == 422
