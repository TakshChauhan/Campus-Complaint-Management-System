"""S3-32: feed visibility matrix for every viewer type in section 2 (Model 2).

Section 2 lists five viewer types. This file expands them into the eleven
concrete callers that the implemented rules can tell apart, builds ONE shared
corpus of complaints in every publication state, and checks what each caller
can reach on every read route:

    GET /feeds/departments/{id}   department feeds (non-Hostel departments)
    GET /feeds/hostel             hostel feed (HMC-scoped complaints)
    GET /feeds/items/{id}         single feed item

Viewers
-------
  alice               student, verified residence A1 (HMC group AB1)
  bob                 student, verified residence C1 (HMC group C1)
  nh_resident         student, verified residence in the New Hostel (group N1)
  pending             student, residence pending
  rejected            student, residence rejected
  no_residence        student, never declared a residence
  unmapped_resident   student, verified residence on a floor with no HMC group
  hostel_staff        staff in the Hostel department
  admin               administrator
  it_staff            staff in another department ("other staff")
  no_dept_staff       staff with no department ("other staff")

The expected results below are written out by hand from API contract 7.7, 7.8,
7.10 and 7.11.9 (docs/API_CONTRACT.md). They are NOT computed with the
application's own visibility helpers, so a bug in those helpers cannot hide
itself here.

Contract note: the Model 2 plan in the sprint brief described a hostel-wide
student feed with ``scope=hostel|wing|floor``. ``main`` implements the
Sprint 4 decision instead (API contract 7.8): students see only complaints
published for their own verified HMC group, and there is no ``scope``
parameter. ``test_unsupported_scope_parameter_never_widens_a_students_feed``
pins that a client still sending ``scope`` gains nothing.

Run just this file:   pytest tests/test_sprint3_visibility_matrix.py -v
"""
import pytest

from app.models.complaint import Complaint
from app.models.department import Department
from sprint3_hmc_world import (
    FEED_ITEM_KEYS, FORBIDDEN_FEED_KEYS, HOSTEL_FEED_ITEM_KEYS, build_world, headers_for, make_user,
    set_residence, submit,
)

HOSTEL_FEED = "/api/v1/feeds/hostel"
DETAIL = "/api/v1/feeds/items/{}"
LEAK_MARKER = "PRIVATE-DETAIL"  # appears only in complaint descriptions
HOSTEL_ID_STAFF_ONLY = ("hostel_staff", "admin")


def dept_feed(department_id: int) -> str:
    return f"/api/v1/feeds/departments/{department_id}"


# --------------------------------------------------------------------------- #
# Expected results, written by hand from the contract
# --------------------------------------------------------------------------- #

STUDENT_VIEWERS = ["alice", "bob", "nh_resident", "pending", "rejected", "no_residence", "unmapped_resident"]
STAFF_VIEWERS = ["hostel_staff", "admin", "it_staff", "no_dept_staff"]
ALL_VIEWERS = STUDENT_VIEWERS + STAFF_VIEWERS

# Publication result of each corpus complaint after the moderation steps in the
# ``corpus`` fixture. Asserting this while building the corpus means a change
# to the classification rules fails loudly there instead of silently shifting
# every expectation below.
CORPUS_PUBLICATION = {
    "it_public": "published",
    "lib_public": "published",
    "it_private": "private",
    "hostel_a1": "published",
    "hostel_a1_private": "private",
    "it_a1": "published",
    "hostel_c1": "published",
    "hostel_b1_pending": "pending_review",
    "hostel_b1_approved": "published",
    "hostel_a1_rejected": "rejected",
    "hostel_a1_unpublished": "rejected",
    "hostel_d1_unmapped": "pending_mapping",
    "hostel_unlocated": "pending_mapping",
    "it_legacy_text_location": "pending_mapping",
    "nh_n1": "published",
    "shared_c1_to_ab1": "published",
    "parking_a1_inactive_dept": "published",
}

# Department-wide items: every signed-in user reads these, nobody else's.
DEPARTMENT_FEED_EXPECTED = {"it": {"it_public"}, "library": {"lib_public"}}
DEPARTMENT_WIDE = {"it_public", "lib_public"}

# Hostel feed (HMC-scoped) per viewer. ``parking_a1_inactive_dept`` is published
# for AB1 but its department is inactive, so it is excluded for everyone.
HOSTEL_FEED_EXPECTED = {
    "alice": {"hostel_a1", "it_a1", "hostel_b1_approved", "shared_c1_to_ab1"},
    "bob": {"hostel_c1", "shared_c1_to_ab1"},
    "nh_resident": {"nh_n1"},
    "hostel_staff": {"hostel_a1", "it_a1", "hostel_b1_approved", "hostel_c1", "shared_c1_to_ab1", "nh_n1"},
    "admin": {"hostel_a1", "it_a1", "hostel_b1_approved", "hostel_c1", "shared_c1_to_ab1", "nh_n1"},
}
# Viewers that receive 403 residence_not_verified (no fallback to a wider view).
RESIDENCE_NOT_VERIFIED = {"pending", "rejected", "no_residence", "unmapped_resident"}
# "Other staff": 403 with a plain string detail.
OTHER_STAFF = {"it_staff", "no_dept_staff"}

NEVER_VISIBLE = {
    "it_private", "hostel_a1_private", "hostel_b1_pending", "hostel_a1_rejected", "hostel_a1_unpublished",
    "hostel_d1_unmapped", "hostel_unlocated", "it_legacy_text_location", "parking_a1_inactive_dept",
}

# Lifecycle status set on some complaints for the status-filter test.
CORPUS_STATUS = {"hostel_a1": "resolved", "it_a1": "in_progress", "hostel_c1": "reopened"}


def visible_names(viewer: str) -> set[str]:
    """Everything the single-item route must return for this viewer."""
    return DEPARTMENT_WIDE | HOSTEL_FEED_EXPECTED.get(viewer, set())


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    """The matrix builds many users; skip bcrypt (no test here logs in with a password)."""
    monkeypatch.setattr("sprint3_hmc_world.get_password_hash", lambda _password: "not-a-real-hash")


@pytest.fixture
def departments(db):
    rows = {
        "it": Department(name="IT Services", description="IT", is_active=True),
        "hostel": Department(name="Hostel", description="Hostel", is_active=True),
        "library": Department(name="Library", description="Library", is_active=True),
        "parking": Department(name="Parking", description="Parking", is_active=True),
    }
    db.add_all(rows.values())
    db.commit()
    return rows


@pytest.fixture
def world(db, departments):
    alice = make_user(db, "alice", "student")
    bob = make_user(db, "bob", "student")
    return build_world(db, departments, alice, bob) | {"alice": alice, "bob": bob}


@pytest.fixture
def users(db, world):
    """Every viewer's user row, with the residence each one needs."""
    floors, staff = world["floors"], world["hostel_staff"]
    cast = {
        "alice": world["alice"],  # verified A1 by build_world
        "bob": world["bob"],  # verified C1 by build_world
        "hostel_staff": staff,
        "it_staff": world["it_staff"],
        "admin": make_user(db, "chief.admin", "admin"),
        "no_dept_staff": make_user(db, "nodept.staff", "staff"),
        "no_residence": make_user(db, "no.residence", "student"),
    }
    cast["nh_resident"] = make_user(db, "nh.resident", "student")
    set_residence(db, cast["nh_resident"], floors["N1"], staff)
    cast["pending"] = make_user(db, "pending.student", "student")
    set_residence(db, cast["pending"], floors["A1"], None, status="pending")
    cast["rejected"] = make_user(db, "rejected.student", "student")
    set_residence(db, cast["rejected"], floors["A1"], staff, status="rejected")
    cast["unmapped_resident"] = make_user(db, "unmapped.student", "student")
    set_residence(db, cast["unmapped_resident"], floors["D1"], staff)
    return cast


@pytest.fixture
def headers(users):
    return {viewer: headers_for(user) for viewer, user in users.items()}


@pytest.fixture
def corpus(client, db, world, departments, users, headers):
    """Complaint ids by name, covering every publication state and department type."""
    floors = world["floors"]
    it, hostel, library, parking = (departments[k].id for k in ("it", "hostel", "library", "parking"))
    admin = headers["admin"]
    created: dict[str, int] = {}
    reported: dict[str, str] = {}

    def make(key, who, department_id, **extra):
        response = submit(
            client, headers[who], department_id, f"Matrix {key}",
            description=f"{LEAK_MARKER} {key}: reporter-only detail that no feed may repeat.", **extra,
        )
        assert response.status_code == 201, f"{key}: {response.text}"
        created[key] = response.json()["id"]
        reported[key] = response.json()["publication_status"]

    make("it_public", "alice", it)
    make("lib_public", "bob", library)
    make("it_private", "alice", it, is_public=False)
    make("hostel_a1", "alice", hostel, floor_id=floors["A1"].id)
    make("hostel_a1_private", "alice", hostel, floor_id=floors["A1"].id, is_public=False)
    make("it_a1", "alice", it, floor_id=floors["A1"].id)
    make("hostel_c1", "bob", hostel, floor_id=floors["C1"].id)
    make("hostel_b1_pending", "bob", hostel, floor_id=floors["B1"].id)  # Bob is not in AB1
    make("hostel_b1_approved", "bob", hostel, floor_id=floors["B1"].id)
    make("hostel_a1_rejected", "bob", hostel, floor_id=floors["A1"].id)
    make("hostel_a1_unpublished", "alice", hostel, floor_id=floors["A1"].id)
    make("hostel_d1_unmapped", "bob", hostel, floor_id=floors["D1"].id)
    make("hostel_unlocated", "alice", hostel)
    make("it_legacy_text_location", "alice", it, hostel="Main Hostel")
    make("nh_n1", "nh_resident", hostel, floor_id=floors["N1"].id)
    make("shared_c1_to_ab1", "bob", hostel, floor_id=floors["C1"].id)
    make("parking_a1_inactive_dept", "alice", parking, floor_id=floors["A1"].id)

    approved = client.post(f"/api/v1/hmc/publication-requests/{created['hostel_b1_approved']}/decision",
                           headers=admin, json={"decision": "approved"})
    assert approved.status_code == 200, approved.text
    rejected = client.post(f"/api/v1/hmc/publication-requests/{created['hostel_a1_rejected']}/decision",
                           headers=admin, json={"decision": "rejected", "note": "Not substantiated."})
    assert rejected.status_code == 200, rejected.text
    unpublished = client.post(f"/api/v1/hmc/complaints/{created['hostel_a1_unpublished']}/unpublish",
                              headers=admin, json={"note": "Reported in error."})
    assert unpublished.status_code == 200, unpublished.text
    shared = client.post(f"/api/v1/hmc/complaints/{created['shared_c1_to_ab1']}/audiences", headers=admin,
                         json={"hmc_group_id": world["groups"]["AB1"].id, "note": "Common corridor for A, B and C."})
    assert shared.status_code == 200, shared.text
    departments["parking"].is_active = False
    for key, lifecycle in CORPUS_STATUS.items():
        db.query(Complaint).filter(Complaint.id == created[key]).update({"status": lifecycle})
    db.commit()

    for key, publication in CORPUS_PUBLICATION.items():
        stored = db.query(Complaint).filter(Complaint.id == created[key]).one()
        assert stored.publication_status == publication, f"corpus precondition: {key} is {stored.publication_status}"
    assert set(created) == set(CORPUS_PUBLICATION)
    return created


def ids_of(corpus: dict[str, int], names: set[str]) -> set[int]:
    return {corpus[name] for name in names}


def feed_item_ids(response) -> set[int]:
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


# --------------------------------------------------------------------------- #
# 1. Department feeds
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("viewer", ALL_VIEWERS)
def test_department_feeds_show_every_viewer_all_public_department_complaints_and_nothing_else(
    client, corpus, departments, headers, viewer,
):
    """Section 2: 'every signed-in user can read' department feeds, whoever they are."""
    for key, expected in DEPARTMENT_FEED_EXPECTED.items():
        response = client.get(dept_feed(departments[key].id), headers=headers[viewer])
        assert feed_item_ids(response) == ids_of(corpus, expected), key
        assert response.headers["X-Total-Count"] == str(len(expected))


@pytest.mark.parametrize("viewer", ALL_VIEWERS)
def test_hostel_department_is_never_served_by_the_department_feed(client, corpus, departments, headers, viewer):
    response = client.get(dept_feed(departments["hostel"].id), headers=headers[viewer])
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "hostel_feed_required"


@pytest.mark.parametrize("viewer", ALL_VIEWERS)
def test_department_feed_hides_hostel_located_complaints_of_other_departments(
    client, corpus, departments, headers, viewer,
):
    """IT complaints with a floor, legacy hostel text or an inactive department never reach a department feed."""
    it_feed = feed_item_ids(client.get(dept_feed(departments["it"].id), headers=headers[viewer]))
    assert corpus["it_a1"] not in it_feed
    assert corpus["it_legacy_text_location"] not in it_feed
    assert client.get(dept_feed(departments["parking"].id), headers=headers[viewer]).status_code == 404


# --------------------------------------------------------------------------- #
# 2. Hostel feed
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("viewer", ALL_VIEWERS)
def test_hostel_feed_matrix(client, corpus, headers, viewer):
    response = client.get(HOSTEL_FEED, headers=headers[viewer])
    if viewer in RESIDENCE_NOT_VERIFIED:
        assert response.status_code == 403, response.text
        assert response.json()["detail"]["code"] == "residence_not_verified"
        assert response.headers.get("X-Total-Count") is None  # no data, not even a count
    elif viewer in OTHER_STAFF:
        assert response.status_code == 403, response.text
        assert isinstance(response.json()["detail"], str)
    else:
        expected = HOSTEL_FEED_EXPECTED[viewer]
        assert feed_item_ids(response) == ids_of(corpus, expected)
        assert response.headers["X-Total-Count"] == str(len(expected))
        assert not ids_of(corpus, NEVER_VISIBLE) & feed_item_ids(response)


@pytest.mark.parametrize("viewer", sorted(HOSTEL_FEED_EXPECTED))
def test_hostel_feed_items_carry_canonical_location_names(client, corpus, headers, viewer):
    names = {
        corpus["hostel_a1"]: ("Main Hostel", "Wing A", "Floor 1"),
        corpus["it_a1"]: ("Main Hostel", "Wing A", "Floor 1"),
        corpus["hostel_b1_approved"]: ("Main Hostel", "Wing B", "Floor 1"),
        corpus["hostel_c1"]: ("Main Hostel", "Wing C", "Floor 1"),
        corpus["shared_c1_to_ab1"]: ("Main Hostel", "Wing C", "Floor 1"),
        corpus["nh_n1"]: ("New Hostel", "Wing N", "Floor 1"),
    }
    for item in client.get(HOSTEL_FEED, headers=headers[viewer]).json():
        assert (item["hostel"], item["wing"], item["floor"]) == names[item["id"]]


def test_student_group_membership_follows_the_floor_not_the_hostel_or_the_wing(client, corpus, headers):
    """Alice (A1, AB1) sees Wing B floor 1 (same group) but not Wing C floor 1 unless explicitly shared."""
    alice = client.get(HOSTEL_FEED, headers=headers["alice"]).json()
    wings = {item["wing"] for item in alice}
    assert wings == {"Wing A", "Wing B", "Wing C"}
    assert corpus["hostel_c1"] not in {item["id"] for item in alice}  # Wing C item arrives only via the shared row
    bob = {item["id"] for item in client.get(HOSTEL_FEED, headers=headers["bob"]).json()}
    assert not bob & ids_of(corpus, {"hostel_a1", "it_a1", "hostel_b1_approved"})


@pytest.mark.parametrize("viewer", ["hostel_staff", "admin"])
def test_staff_and_admin_see_exactly_the_union_of_what_the_group_members_see(client, corpus, headers, viewer):
    """Nothing is visible to staff that no group was authorized to see, and no group's item is missing."""
    union = set()
    for member in ("alice", "bob", "nh_resident"):
        union |= feed_item_ids(client.get(HOSTEL_FEED, headers=headers[member]))
    assert feed_item_ids(client.get(HOSTEL_FEED, headers=headers[viewer])) == union == ids_of(
        corpus, HOSTEL_FEED_EXPECTED[viewer])


@pytest.mark.parametrize("viewer", ALL_VIEWERS)
def test_hostel_feed_is_unavailable_when_the_hostel_department_is_inactive(
    client, db, corpus, departments, headers, viewer,
):
    departments["hostel"].is_active = False
    db.commit()
    assert client.get(HOSTEL_FEED, headers=headers[viewer]).status_code == 404


# --------------------------------------------------------------------------- #
# 3. hostel_id and the unsupported scope parameter
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("viewer", STUDENT_VIEWERS)
def test_every_student_type_is_refused_when_selecting_a_hostel(client, corpus, world, headers, viewer):
    """Rejected before residence is looked at, so even unverified students learn nothing."""
    response = client.get(f"{HOSTEL_FEED}?hostel_id={world['new'].id}", headers=headers[viewer])
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "hostel_selection_forbidden"


@pytest.mark.parametrize("viewer", sorted(OTHER_STAFF))
def test_other_staff_cannot_use_hostel_id_to_get_in(client, corpus, world, headers, viewer):
    assert client.get(f"{HOSTEL_FEED}?hostel_id={world['main'].id}", headers=headers[viewer]).status_code == 403


@pytest.mark.parametrize("viewer", HOSTEL_ID_STAFF_ONLY)
def test_hostel_id_restricts_staff_and_admin_to_one_hostel(client, corpus, world, headers, viewer):
    main = feed_item_ids(client.get(f"{HOSTEL_FEED}?hostel_id={world['main'].id}", headers=headers[viewer]))
    new = feed_item_ids(client.get(f"{HOSTEL_FEED}?hostel_id={world['new'].id}", headers=headers[viewer]))
    assert main == ids_of(corpus, HOSTEL_FEED_EXPECTED[viewer] - {"nh_n1"})
    assert new == ids_of(corpus, {"nh_n1"})
    assert not main & new
    unknown = client.get(f"{HOSTEL_FEED}?hostel_id=999999", headers=headers[viewer])
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "hostel_not_found"


@pytest.mark.parametrize("scope", ["hostel", "wing", "floor", "all", "nh"])
@pytest.mark.parametrize("viewer", ["alice", "bob", "nh_resident"])
def test_unsupported_scope_parameter_never_widens_a_students_feed(client, corpus, headers, viewer, scope):
    plain = feed_item_ids(client.get(HOSTEL_FEED, headers=headers[viewer]))
    scoped = feed_item_ids(client.get(f"{HOSTEL_FEED}?scope={scope}", headers=headers[viewer]))
    assert scoped == plain == ids_of(corpus, HOSTEL_FEED_EXPECTED[viewer])


@pytest.mark.parametrize("viewer", sorted(RESIDENCE_NOT_VERIFIED))
def test_unsupported_scope_parameter_does_not_open_the_feed_for_unverified_students(client, corpus, headers, viewer):
    for scope in ("hostel", "wing", "floor"):
        response = client.get(f"{HOSTEL_FEED}?scope={scope}", headers=headers[viewer])
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "residence_not_verified"


# --------------------------------------------------------------------------- #
# 4. Single feed item: the same rules, applied per complaint
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("viewer", ALL_VIEWERS)
def test_feed_item_route_matches_the_feeds_for_every_complaint(client, corpus, headers, viewer):
    allowed = visible_names(viewer)
    for name, complaint_id in corpus.items():
        response = client.get(DETAIL.format(complaint_id), headers=headers[viewer])
        if name in allowed:
            assert response.status_code == 200, f"{viewer} should see {name}: {response.text}"
            assert response.json()["id"] == complaint_id
        else:
            assert response.status_code == 404, f"{viewer} must not see {name}: {response.status_code}"


@pytest.mark.parametrize("viewer", ALL_VIEWERS)
def test_hidden_and_nonexistent_complaints_are_indistinguishable(client, corpus, headers, viewer):
    """A 404 must not reveal whether a hidden complaint exists."""
    nonexistent = client.get(DETAIL.format(999999), headers=headers[viewer])
    assert nonexistent.status_code == 404
    for name in NEVER_VISIBLE | (set(corpus) - visible_names(viewer)):
        hidden = client.get(DETAIL.format(corpus[name]), headers=headers[viewer])
        assert (hidden.status_code, hidden.json()) == (nonexistent.status_code, nonexistent.json()), name


@pytest.mark.parametrize("viewer", ALL_VIEWERS)
def test_department_wide_items_have_no_location_in_detail(client, corpus, headers, viewer):
    for name in DEPARTMENT_WIDE:
        item = client.get(DETAIL.format(corpus[name]), headers=headers[viewer]).json()
        assert (item["hostel"], item["wing"], item["floor"]) == (None, None, None)


@pytest.mark.parametrize("viewer", ALL_VIEWERS)
def test_a_hostel_department_record_wrongly_stored_as_department_wide_is_still_hidden(
    client, db, corpus, departments, users, headers, viewer,
):
    """Defence in depth: bad data (old import, manual edit) must not turn a Hostel complaint into a campus-wide one.

    The department feed already answers 400 for the Hostel department, so the single-item
    route and the hostel feed are the places such a record could leak.
    """
    stray = Complaint(
        title="Stray hostel record", description=f"{LEAK_MARKER} stray", department_id=departments["hostel"].id,
        created_by_id=users["alice"].id, is_public=True, visibility_scope="department_public",
        feed_review_status="not_required", publication_status="published",
    )
    db.add(stray)
    db.commit()
    assert client.get(DETAIL.format(stray.id), headers=headers[viewer]).status_code == 404
    response = client.get(HOSTEL_FEED, headers=headers[viewer])
    if response.status_code == 200:
        assert stray.id not in feed_item_ids(response)


# --------------------------------------------------------------------------- #
# 5. Filters, paging and ordering are applied after visibility, per viewer
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("status", ["submitted", "in_progress", "resolved", "reopened"])
@pytest.mark.parametrize("viewer", sorted(HOSTEL_FEED_EXPECTED))
def test_status_filter_never_reveals_items_outside_the_viewers_set(client, corpus, headers, viewer, status):
    expected = {name for name in HOSTEL_FEED_EXPECTED[viewer] if CORPUS_STATUS.get(name, "submitted") == status}
    response = client.get(f"{HOSTEL_FEED}?status={status}", headers=headers[viewer])
    assert feed_item_ids(response) == ids_of(corpus, expected)
    assert response.headers["X-Total-Count"] == str(len(expected))


def test_status_filter_rejects_unknown_values_for_every_feed(client, corpus, departments, headers):
    for path in (HOSTEL_FEED, dept_feed(departments["it"].id)):
        assert client.get(f"{path}?status=approved", headers=headers["alice"]).status_code == 422


@pytest.mark.parametrize("viewer", sorted(HOSTEL_FEED_EXPECTED))
def test_total_count_ignores_paging_and_ordering_is_newest_first(client, corpus, headers, viewer):
    expected = HOSTEL_FEED_EXPECTED[viewer]
    full = client.get(HOSTEL_FEED, headers=headers[viewer]).json()
    assert [item["id"] for item in full] == [
        item["id"] for item in sorted(full, key=lambda i: (i["created_at"], i["id"]), reverse=True)
    ]
    first = client.get(f"{HOSTEL_FEED}?limit=1", headers=headers[viewer])
    assert len(first.json()) == 1
    assert first.json()[0]["id"] == full[0]["id"]
    assert first.headers["X-Total-Count"] == str(len(expected))
    rest = client.get(f"{HOSTEL_FEED}?limit=100&offset=1", headers=headers[viewer])
    assert [item["id"] for item in rest.json()] == [item["id"] for item in full[1:]]
    beyond = client.get(f"{HOSTEL_FEED}?offset=1000", headers=headers[viewer])
    assert beyond.json() == [] and beyond.headers["X-Total-Count"] == str(len(expected))


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "limit=abc"])
def test_invalid_paging_is_rejected_before_any_data_is_read(client, corpus, headers, query):
    assert client.get(f"{HOSTEL_FEED}?{query}", headers=headers["alice"]).status_code == 422
    assert client.get(f"{HOSTEL_FEED}?{query}", headers=headers["pending"]).status_code == 422


# --------------------------------------------------------------------------- #
# 6. Authentication
# --------------------------------------------------------------------------- #

def test_anonymous_callers_reach_no_feed_route(client, corpus, departments):
    paths = [HOSTEL_FEED, dept_feed(departments["it"].id), dept_feed(departments["hostel"].id),
             DETAIL.format(corpus["it_public"]), DETAIL.format(corpus["hostel_a1"])]
    for path in paths:
        assert client.get(path).status_code == 401, path


@pytest.mark.parametrize("viewer", ["alice", "hostel_staff", "admin"])
def test_deactivated_accounts_lose_every_feed(client, db, corpus, departments, users, headers, viewer):
    users[viewer].is_active = False
    db.commit()
    paths = [HOSTEL_FEED, dept_feed(departments["it"].id), DETAIL.format(corpus["it_public"])]
    for path in paths:
        assert client.get(path, headers=headers[viewer]).status_code == 403, path


# --------------------------------------------------------------------------- #
# 7. Response shape for every viewer
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("viewer", ALL_VIEWERS)
def test_feeds_expose_only_contract_fields_to_every_viewer(client, corpus, departments, headers, viewer):
    """Same shape for students, staff and admin: no description, reporter identity or moderation data."""
    responses = [
        (client.get(dept_feed(departments["it"].id), headers=headers[viewer]), FEED_ITEM_KEYS),
        (client.get(dept_feed(departments["library"].id), headers=headers[viewer]), FEED_ITEM_KEYS),
        (client.get(HOSTEL_FEED, headers=headers[viewer]), HOSTEL_FEED_ITEM_KEYS),
    ]
    for name in visible_names(viewer):
        responses.append((client.get(DETAIL.format(corpus[name]), headers=headers[viewer]), HOSTEL_FEED_ITEM_KEYS))
    for response, allowed_keys in responses:
        if response.status_code != 200:
            continue
        body = response.json()
        for item in body if isinstance(body, list) else [body]:
            assert set(item) == allowed_keys
            assert not FORBIDDEN_FEED_KEYS & set(item)
        for leak in (LEAK_MARKER, "@campus.edu", "Student Alice", "Student Bob", "publication_status",
                     "visibility_scope", "feed_review", "hmc_group", "floor_id"):
            assert leak not in response.text, f"{viewer} response leaked {leak!r}"
