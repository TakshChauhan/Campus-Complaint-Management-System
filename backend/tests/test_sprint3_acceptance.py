"""S3-34: Sprint 3 backend acceptance tests (Deep - backend tests deliverable).

Where S3-32 (visibility matrix) and S3-33 (privacy) look at one rule at a time,
these tests check that Sprint 3 works as a whole, through the HTTP API only,
the way a resident and the Hostel staff would use it. They are grouped by the
Sprint 3 acceptance areas:

1. Contract surface   - every API contract v3 route exists and answers the right roles
2. Database           - Sprint 3 migrations 0008-0013 remain valid through the current head
3. Resident journey   - declare residence -> staff verify -> report -> feed -> duplicate warning
4. Residence rules    - pending / verified / rejected, re-verification, 409 on double decision
5. Complaint location - floor_id handling for Hostel and other departments
6. Privacy in context - private complaints and identity never surface during the journey
7. Resolution         - staff progress shows in the feeds; hostel resolution metrics
8. Staff and admin    - the hostel-wide view, hostel_id filtering, other staff blocked

Updated for Sprint 4 Model 2 (API_CONTRACT.md sections 7.8 and 11):

* verified residents see the hostel-wide feed, with optional
  ``scope=hostel|wing|floor`` narrowing to their own wing or floor;
* a residence is changed with ``PATCH /users/me/residence`` (the brief said PUT);
* new Hostel complaints require ``floor_id`` by default; a legacy-mode override
  is tested separately without relaxing the production requirement;
* ``GET /admin/metrics/resolution`` is implemented and is tested as a real route.

Run just this file:   pytest tests/test_sprint3_acceptance.py -v
"""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.main import app
from app.models.complaint import Complaint
from app.models.department import Department
from app.models.student_residence import StudentResidence
from app.services.complaint_lifecycle_service import calculate_hostel_resolution_metrics
from sprint3_hmc_world import (
    FEED_ITEM_KEYS, FORBIDDEN_FEED_KEYS, HOSTEL_FEED_ITEM_KEYS, build_world, headers_for, make_user, set_residence,
    submit,
)

API = "/api/v1"
LOCATIONS = f"{API}/locations/hostels"
MY_RESIDENCE = f"{API}/users/me/residence"
RESIDENCE_QUEUE = f"{API}/staff/residences"
HOSTEL_FEED = f"{API}/feeds/hostel"
DUPLICATES = f"{API}/complaints/duplicate-suggestions"
METRICS_PATH = f"{API}/admin/metrics/resolution"
BACKEND_DIR = Path(__file__).resolve().parents[1]

LEAK_MARKER = "PRIVATE-DETAIL"
REPORT_TITLE = "Corridor router offline"
REPORT_TEXT = f"{LEAK_MARKER} The corridor router is offline and the network connectivity is disrupted all day."


def dept_feed(department_id: int) -> str:
    return f"{API}/feeds/departments/{department_id}"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    monkeypatch.setattr("sprint3_hmc_world.get_password_hash", lambda _password: "not-a-real-hash")


@pytest.fixture
def departments(db):
    rows = {
        "it": Department(name="IT Services", description="IT", is_active=True),
        "hostel": Department(name="Hostel", description="Hostel", is_active=True),
        "library": Department(name="Library", description="Library", is_active=True),
    }
    db.add_all(rows.values())
    db.commit()
    return rows


@pytest.fixture
def world(db, departments):
    alice = make_user(db, "alice", "student")  # verified, Main Hostel, Wing A floor 1
    bob = make_user(db, "bob", "student")  # same hostel, another wing (Wing C floor 1)
    return build_world(db, departments, alice, bob) | {"alice": alice, "bob": bob}


@pytest.fixture
def people(db, world):
    """Everyone the journey needs. ``newcomer`` has never declared a residence."""
    carol = make_user(db, "carol", "student")  # same hostel as Alice, another wing (Wing B)
    set_residence(db, carol, world["floors"]["B1"], world["hostel_staff"])
    nh = make_user(db, "nh.resident", "student")
    set_residence(db, nh, world["floors"]["N1"], world["hostel_staff"])
    return {
        "alice": world["alice"], "bob": world["bob"], "carol": carol, "nh": nh,
        "newcomer": make_user(db, "newcomer", "student"),
        "hostel_staff": world["hostel_staff"], "it_staff": world["it_staff"],
        "admin": make_user(db, "chief.admin", "admin"),
    }


@pytest.fixture
def hdr(people):
    return {key: headers_for(user) for key, user in people.items()}


def report(client, headers, department_id, title=REPORT_TITLE, **extra):
    response = submit(client, headers, department_id, title, description=REPORT_TEXT, **extra)
    assert response.status_code == 201, response.text
    return response.json()


def ids(response) -> set[int]:
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


def duplicate_ids(client, headers) -> set[int]:
    response = client.post(DUPLICATES, headers=headers, json={"title": REPORT_TITLE, "description": REPORT_TEXT})
    assert response.status_code == 200, response.text
    return {match["id"] for match in response.json()["matches"]}


# =========================================================================== #
# 1. CONTRACT SURFACE
# =========================================================================== #

V3_ROUTES = [
    ("get", "/api/v1/locations/hostels"),
    ("get", "/api/v1/users/me/residence"),
    ("patch", "/api/v1/users/me/residence"),
    ("get", "/api/v1/staff/residences"),
    ("post", "/api/v1/staff/residences/{residence_id}/decision"),
    ("post", "/api/v1/complaints"),
    ("get", "/api/v1/feeds/departments/{department_id}"),
    ("get", "/api/v1/feeds/hostel"),
    ("get", "/api/v1/feeds/items/{complaint_id}"),
]


@pytest.mark.parametrize("method,path", V3_ROUTES, ids=[f"{m.upper()} {p.removeprefix('/api/v1')}" for m, p in V3_ROUTES])
def test_every_contract_v3_route_is_published_in_the_openapi_document(method, path):
    assert method in app.openapi()["paths"].get(path, {}), f"{method.upper()} {path} is missing"


# role -> expected status; "anon" sends no token. ``alice`` is a verified resident,
# ``newcomer`` a student with no residence, ``it_staff`` is "other staff".
ACCESS_MATRIX = {
    "GET /locations/hostels": {"alice": 200, "newcomer": 200, "hostel_staff": 200, "it_staff": 200, "admin": 200, "anon": 401},
    "GET /users/me/residence": {"alice": 200, "newcomer": 404, "hostel_staff": 403, "it_staff": 403, "admin": 403, "anon": 401},
    "PATCH /users/me/residence": {"newcomer": 200, "hostel_staff": 403, "it_staff": 403, "admin": 403, "anon": 401},
    "GET /staff/residences": {"alice": 403, "newcomer": 403, "hostel_staff": 200, "it_staff": 403, "admin": 200, "anon": 401},
    "POST /staff/residences/999999/decision": {"alice": 403, "hostel_staff": 404, "it_staff": 403, "admin": 404, "anon": 401},
    "POST /complaints": {"alice": 201, "hostel_staff": 403, "it_staff": 403, "admin": 403, "anon": 401},
    "GET /feeds/departments/{it}": {"alice": 200, "newcomer": 200, "hostel_staff": 200, "it_staff": 200, "admin": 200, "anon": 401},
    "GET /feeds/hostel": {"alice": 200, "newcomer": 403, "hostel_staff": 200, "it_staff": 403, "admin": 200, "anon": 401},
}


@pytest.mark.parametrize("route", sorted(ACCESS_MATRIX))
def test_contract_v3_access_matrix(client, world, people, hdr, departments, route):
    method, path = route.split(" ", 1)
    path = path.replace("{it}", str(departments["it"].id))
    body = None
    if route == "PATCH /users/me/residence":
        body = {"floor_id": world["floors"]["A2"].id}
    elif route.startswith("POST /staff/residences"):
        body = {"decision": "approve"}
    elif route == "POST /complaints":
        body = {"title": "Campus Wi-Fi outage", "description": "The Wi-Fi has been down since morning.",
                "department_id": departments["it"].id, "is_public": True}
    for role, expected in ACCESS_MATRIX[route].items():
        headers = {} if role == "anon" else hdr[role]
        response = client.request(method, f"{API}{path}", headers=headers, **({"json": body} if body else {}))
        assert response.status_code == expected, f"{route} as {role}: {response.status_code} {response.text}"


def test_admin_resolution_metrics_route_is_available(client, hdr):
    """The merged admin metrics route exists and enforces role/query validation."""
    assert any(getattr(route, "path", None) == METRICS_PATH for route in app.routes)
    assert client.get(METRICS_PATH).status_code == 401
    for viewer in ("alice", "newcomer", "hostel_staff", "it_staff"):
        assert client.get(METRICS_PATH, headers=hdr[viewer]).status_code == 403, viewer
    assert client.get(METRICS_PATH, headers=hdr["admin"]).status_code == 200
    assert client.get(f"{METRICS_PATH}?window_days=0", headers=hdr["admin"]).status_code == 422


# =========================================================================== #
# 2. DATABASE (Sprint 3 migrations 0008-0013 within the current head)
# =========================================================================== #

SPRINT3_REVISIONS = [
    "0008_hostel_locations", "0009_student_residences", "0010_complaint_floor_location",
    "0011_public_feed_hmc", "0012_complaint_hmc_audiences", "0013_backfill_complaint_floor_ids",
]


@pytest.fixture
def migrated(tmp_path):
    url = f"sqlite:///{tmp_path / 'sprint3_acceptance.db'}"
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    yield config, engine
    engine.dispose()


def test_sprint3_migrations_form_one_unbroken_chain_ending_at_head(migrated):
    config, _ = migrated
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1
    chain = [revision.revision for revision in script.walk_revisions()][::-1]
    positions = [chain.index(revision) for revision in SPRINT3_REVISIONS]
    assert positions == list(range(positions[0], positions[0] + len(SPRINT3_REVISIONS)))


def test_migrated_schema_has_the_tables_and_columns_the_contract_describes(migrated):
    _, engine = migrated
    inspector = inspect(engine)

    def columns(table):
        return {column["name"] for column in inspector.get_columns(table)}

    assert columns("hostels") >= {"id", "code", "name", "is_active"}
    assert columns("hostel_wings") >= {"id", "hostel_id", "code", "name", "is_active"}
    assert columns("hostel_floors") >= {"id", "wing_id", "code", "name", "is_active"}
    assert columns("student_residences") >= {
        "id", "student_id", "floor_id", "status", "remark", "verified_by_id", "verified_at"}
    assert columns("complaints") >= {"floor_id", "visibility_scope", "publication_status", "is_public"}
    assert {"hmc_groups", "hmc_group_floors", "hmc_group_moderators", "complaint_hmc_audiences",
            "complaint_publication_audit"} <= set(inspector.get_table_names())


def test_migrated_schema_enforces_unique_codes_one_residence_per_student_and_valid_status(migrated):
    _, engine = migrated
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, name, email, role) VALUES "
                          "(1, 'S', 's@campus.edu', 'student'), (2, 'T', 't@campus.edu', 'student')"))
        conn.execute(text("INSERT INTO hostels (id, code, name) VALUES (1, 'MH', 'Main Hostel')"))
        conn.execute(text("INSERT INTO hostel_wings (id, hostel_id, code, name) VALUES (1, 1, 'A', 'Wing A')"))
        conn.execute(text("INSERT INTO hostel_floors (id, wing_id, code, name) VALUES (1, 1, '1', 'Floor 1')"))
        conn.execute(text("INSERT INTO student_residences (student_id, floor_id, status) VALUES (1, 1, 'pending')"))

    duplicates = {
        "hostel code": "INSERT INTO hostels (code, name) VALUES ('MH', 'Another')",
        "wing code": "INSERT INTO hostel_wings (hostel_id, code, name) VALUES (1, 'A', 'Another')",
        "floor code in a wing": "INSERT INTO hostel_floors (wing_id, code, name) VALUES (1, '1', 'Another')",
        "second residence for a student": "INSERT INTO student_residences (student_id, floor_id) VALUES (1, 1)",
        "unknown residence status": "INSERT INTO student_residences (student_id, floor_id, status) VALUES (2, 1, 'approved')",
    }
    for label, statement in duplicates.items():
        try:
            with engine.begin() as conn:
                conn.execute(text(statement))
        except IntegrityError:
            continue
        pytest.fail(f"the database accepted a duplicate/invalid row: {label}")


# =========================================================================== #
# 3. RESIDENT JOURNEY
# =========================================================================== #

def test_a_new_resident_goes_from_declaring_a_residence_to_a_working_hostel_feed(
    client, db, world, people, hdr, departments,
):
    """The Section 2 story end to end, every step through the public API."""
    newcomer, staff, admin = hdr["newcomer"], hdr["hostel_staff"], hdr["admin"]
    hostel, it = departments["hostel"].id, departments["it"].id
    feed_texts: list[str] = []

    def read_feed(path, headers):
        response = client.get(path, headers=headers)
        feed_texts.append(response.text)
        return response

    # 1. No residence yet: department feeds work, the hostel feed asks for a residence.
    assert client.get(MY_RESIDENCE, headers=newcomer).status_code == 404
    assert read_feed(dept_feed(it), newcomer).status_code == 200
    blocked = read_feed(HOSTEL_FEED, newcomer)
    assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "residence_not_verified"

    # 2. The student picks a floor from the canonical tree and declares it: status becomes pending.
    tree = client.get(LOCATIONS, headers=newcomer).json()
    main = next(h for h in tree if h["code"] == "MH")
    wing_a = next(w for w in main["wings"] if w["code"] == "A")
    floor_a1 = next(f for f in wing_a["floors"] if f["code"] == "1")
    assert floor_a1["id"] == world["floors"]["A1"].id
    declared = client.patch(MY_RESIDENCE, headers=newcomer, json={"floor_id": floor_a1["id"]})
    assert declared.status_code == 200
    assert declared.json() == {"floor_id": floor_a1["id"], "hostel": "Main Hostel", "wing": "Wing A",
                               "floor": "Floor 1", "status": "pending", "remark": None}
    assert read_feed(HOSTEL_FEED, newcomer).status_code == 403  # pending is not enough

    # 3. Hostel staff find it in the pending queue (with a total count) and approve it.
    queue = client.get(f"{RESIDENCE_QUEUE}?status=pending&limit=1", headers=staff)
    assert queue.status_code == 200 and queue.headers["X-Total-Count"] == "1"
    pending = queue.json()[0]
    assert pending["student_email"] == people["newcomer"].email and pending["status"] == "pending"
    approved = client.post(f"{RESIDENCE_QUEUE}/{pending['id']}/decision", headers=staff, json={"decision": "approve"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "verified" and approved.json()["decided_at"] is not None
    assert client.get(MY_RESIDENCE, headers=newcomer).json()["status"] == "verified"
    assert client.get(f"{RESIDENCE_QUEUE}?status=pending", headers=staff).headers["X-Total-Count"] == "0"

    # 4. The verified resident now has a hostel feed (empty so far).
    empty = read_feed(HOSTEL_FEED, newcomer)
    assert empty.status_code == 200 and empty.json() == [] and empty.headers["X-Total-Count"] == "0"

    # 5. They report a Hostel issue on their floor, a campus-wide IT issue and a private one.
    located = report(client, newcomer, hostel, floor_id=floor_a1["id"])
    assert (located["publication_status"], located["visibility_scope"]) == ("published", "hmc_group_public")
    assert located["location"] == {"hostel": "Main Hostel", "wing": "Wing A", "floor": "Floor 1"}
    campus_wide = report(client, newcomer, it)
    assert campus_wide["publication_status"] == "published" and campus_wide["location"] is None
    private = report(client, newcomer, hostel, "Private note about my room", floor_id=floor_a1["id"], is_public=False)
    assert private["publication_status"] == "private"

    # 6. Their own hostel feed shows the located complaint with canonical names - and only that.
    mine = read_feed(HOSTEL_FEED, newcomer)
    assert [item["id"] for item in mine.json()] == [located["id"]]
    assert set(mine.json()[0]) == HOSTEL_FEED_ITEM_KEYS
    assert (mine.json()[0]["hostel"], mine.json()[0]["wing"], mine.json()[0]["floor"]) == ("Main Hostel", "Wing A", "Floor 1")
    it_feed = read_feed(dept_feed(it), hdr["nh"])
    assert [item["id"] for item in it_feed.json()] == [campus_wide["id"]]
    assert set(it_feed.json()[0]) == FEED_ITEM_KEYS
    assert read_feed(dept_feed(hostel), newcomer).status_code == 400  # Hostel complaints never go campus-wide

    # 7. All residents of the same hostel can see it, including other HMC groups.
    for member in ("alice", "bob", "carol"):
        assert located["id"] in ids(read_feed(HOSTEL_FEED, hdr[member]))
        assert client.get(f"{API}/feeds/items/{located['id']}", headers=hdr[member]).status_code == 200
    # Model 2: wing/floor scope narrows Bob's feed, but the default is hostel-wide.
    for scope in ("wing", "floor"):
        assert located["id"] not in ids(read_feed(f"{HOSTEL_FEED}?scope={scope}", hdr["bob"]))
    assert located["id"] not in ids(read_feed(HOSTEL_FEED, hdr["nh"]))
    assert client.get(f"{API}/feeds/items/{located['id']}", headers=hdr["nh"]).status_code == 404

    # 8. Duplicate warnings follow the same hostel privacy boundary.
    for member in ("bob", "carol"):
        assert located["id"] in duplicate_ids(client, hdr[member])
    assert campus_wide["id"] in duplicate_ids(client, hdr["nh"])
    assert located["id"] not in duplicate_ids(client, hdr["nh"])

    # 9. Hostel staff and admin see it too; other staff do not.
    for viewer in ("hostel_staff", "admin"):
        assert located["id"] in ids(read_feed(HOSTEL_FEED, hdr[viewer]))
    assert client.get(HOSTEL_FEED, headers=hdr["it_staff"]).status_code == 403

    # 10. Nothing private ever appeared, and no feed response carried identity or descriptions.
    for text_ in feed_texts:
        for leak in (LEAK_MARKER, "@campus.edu", "Newcomer", "Private note"):
            assert leak not in text_, leak
        for key in FORBIDDEN_FEED_KEYS:
            assert f'"{key}"' not in text_, key

    # 11. Changing residence resets verification and closes the feed until staff
    #     re-verify, without changing who can see the existing hostel complaint.
    moved = client.patch(MY_RESIDENCE, headers=newcomer, json={"floor_id": world["floors"]["B2"].id})
    assert moved.json()["status"] == "pending"
    assert client.get(HOSTEL_FEED, headers=newcomer).status_code == 403
    assert located["id"] in ids(client.get(HOSTEL_FEED, headers=hdr["carol"]))
    assert located["id"] in duplicate_ids(client, newcomer)  # their own complaint stays matchable


# =========================================================================== #
# 4. RESIDENCE RULES
# =========================================================================== #

def test_rejection_carries_a_remark_closes_the_feed_and_can_be_corrected(client, db, world, people, hdr):
    newcomer, staff = hdr["newcomer"], hdr["hostel_staff"]
    client.patch(MY_RESIDENCE, headers=newcomer, json={"floor_id": world["floors"]["C1"].id})
    residence_id = db.query(StudentResidence).filter_by(student_id=people["newcomer"].id).one().id

    assert client.post(f"{RESIDENCE_QUEUE}/{residence_id}/decision", headers=staff,
                       json={"decision": "reject"}).status_code == 422  # remark required
    rejected = client.post(f"{RESIDENCE_QUEUE}/{residence_id}/decision", headers=staff,
                           json={"decision": "reject", "remark": "Allotment list shows Wing D."})
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    mine = client.get(MY_RESIDENCE, headers=newcomer).json()
    assert (mine["status"], mine["remark"]) == ("rejected", "Allotment list shows Wing D.")
    assert client.get(HOSTEL_FEED, headers=newcomer).status_code == 403
    assert client.get(f"{RESIDENCE_QUEUE}?status=rejected", headers=staff).headers["X-Total-Count"] == "1"

    # Correcting the floor resets to pending and clears the old remark.
    corrected = client.patch(MY_RESIDENCE, headers=newcomer, json={"floor_id": world["floors"]["D1"].id})
    assert (corrected.json()["status"], corrected.json()["remark"]) == ("pending", None)
    assert client.post(f"{RESIDENCE_QUEUE}/{residence_id}/decision", headers=staff,
                       json={"decision": "approve"}).status_code == 200
    # D1 has no HMC group, but Model 2 still permits verified residents of its hostel.
    response = client.get(HOSTEL_FEED, headers=newcomer)
    assert response.status_code == 200
    assert response.json() == []


def test_a_decided_residence_cannot_be_decided_again(client, db, world, people, hdr):
    client.patch(MY_RESIDENCE, headers=hdr["newcomer"], json={"floor_id": world["floors"]["A2"].id})
    residence_id = db.query(StudentResidence).filter_by(student_id=people["newcomer"].id).one().id
    path = f"{RESIDENCE_QUEUE}/{residence_id}/decision"
    assert client.post(path, headers=hdr["hostel_staff"], json={"decision": "approve"}).status_code == 200
    for decision in ({"decision": "approve"}, {"decision": "reject", "remark": "Changed my mind."}):
        assert client.post(path, headers=hdr["admin"], json=decision).status_code == 409
    assert client.get(MY_RESIDENCE, headers=hdr["newcomer"]).json()["status"] == "verified"


def test_residence_queue_is_paginated_with_a_total_count(client, db, world, people, hdr):
    extra = [make_user(db, f"queue{i}", "student") for i in range(5)]
    for student in extra:
        assert client.patch(MY_RESIDENCE, headers=headers_for(student),
                            json={"floor_id": world["floors"]["A2"].id}).status_code == 200
    first = client.get(f"{RESIDENCE_QUEUE}?status=pending&limit=2&offset=0", headers=hdr["admin"])
    second = client.get(f"{RESIDENCE_QUEUE}?status=pending&limit=2&offset=2", headers=hdr["admin"])
    last = client.get(f"{RESIDENCE_QUEUE}?status=pending&limit=2&offset=4", headers=hdr["admin"])
    assert [len(page.json()) for page in (first, second, last)] == [2, 2, 1]
    assert {page.headers["X-Total-Count"] for page in (first, second, last)} == {"5"}
    seen = [item["id"] for page in (first, second, last) for item in page.json()]
    assert len(seen) == len(set(seen)) == 5


# =========================================================================== #
# 5. COMPLAINT LOCATION
# =========================================================================== #

def test_hostel_complaints_require_a_floor_by_default_but_legacy_mode_remains_unpublished(
    client, world, hdr, departments, monkeypatch,
):
    # Model 2 default: Hostel complaints without a canonical floor are rejected.
    assert settings.HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID is True
    refused = submit(client, hdr["alice"], departments["hostel"].id, "Hostel fan broken")
    assert refused.status_code == 422

    # If an operator explicitly permits legacy, unlocated reports must remain unpublished.
    with monkeypatch.context() as legacy:
        legacy.setattr(settings, "HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID", False)
        unlocated = report(client, hdr["alice"], departments["hostel"].id, "Legacy hostel fan broken")
    assert unlocated["publication_status"] == "pending_mapping"
    assert unlocated["id"] not in ids(client.get(HOSTEL_FEED, headers=hdr["alice"]))
    assert unlocated["id"] not in ids(client.get(HOSTEL_FEED, headers=hdr["admin"]))

    # The strict default is restored after the legacy-mode check.
    refused = submit(client, hdr["alice"], departments["hostel"].id, "Hostel fan broken again")
    assert refused.status_code == 422
    assert submit(client, hdr["alice"], departments["hostel"].id, "Hostel fan broken again",
                  floor_id=world["floors"]["A1"].id).status_code == 201
    assert submit(client, hdr["alice"], departments["it"].id, "Campus Wi-Fi outage").status_code == 201


def test_unknown_or_inactive_floor_is_rejected_for_any_department(client, db, world, hdr, departments):
    world["floors"]["A3"].is_active = False
    db.commit()
    for department in ("hostel", "it"):
        for floor_id in (world["floors"]["A3"].id, 999999):
            response = submit(client, hdr["alice"], departments[department].id, "Broken light", floor_id=floor_id)
            assert response.status_code == 422, (department, floor_id)
    assert submit(client, hdr["alice"], departments["it"].id, "Broken light", floor_id=0).status_code == 422


def test_a_floor_on_a_non_hostel_complaint_keeps_it_out_of_the_department_feed(client, world, hdr, departments):
    wide = report(client, hdr["alice"], departments["it"].id, "Campus Wi-Fi outage")
    located = report(client, hdr["alice"], departments["it"].id, "Wing A access point dead", floor_id=world["floors"]["A1"].id)
    assert ids(client.get(dept_feed(departments["it"].id), headers=hdr["bob"])) == {wide["id"]}
    assert located["id"] in ids(client.get(HOSTEL_FEED, headers=hdr["alice"]))
    assert located["id"] in ids(client.get(HOSTEL_FEED, headers=hdr["bob"]))
    assert located["id"] not in ids(client.get(f"{HOSTEL_FEED}?scope=wing", headers=hdr["bob"]))
    assert located["id"] not in ids(client.get(HOSTEL_FEED, headers=hdr["nh"]))


# =========================================================================== #
# 6. PRIVACY IN CONTEXT
# =========================================================================== #

def test_private_complaints_appear_in_no_feed_for_any_viewer(client, world, hdr, departments):
    private = [
        report(client, hdr["alice"], departments["hostel"].id, floor_id=world["floors"]["A1"].id, is_public=False),
        report(client, hdr["alice"], departments["it"].id, is_public=False),
        report(client, hdr["alice"], departments["library"].id, is_public=False),
    ]
    private_ids = {item["id"] for item in private}
    assert all(item["publication_status"] == "private" for item in private)
    for viewer in hdr:
        for path in (HOSTEL_FEED, *(dept_feed(d.id) for d in departments.values())):
            response = client.get(path, headers=hdr[viewer])
            if response.status_code == 200:
                assert not private_ids & {item["id"] for item in response.json()}, (viewer, path)
        for complaint_id in private_ids:
            assert client.get(f"{API}/feeds/items/{complaint_id}", headers=hdr[viewer]).status_code == 404, viewer
    # Duplicate warnings: identical text, but only the owner is matched with their own private complaints.
    assert private_ids <= duplicate_ids(client, hdr["alice"])
    for viewer in ("carol", "bob", "nh", "newcomer"):
        assert not private_ids & duplicate_ids(client, hdr[viewer]), viewer


# =========================================================================== #
# 7. RESOLUTION
# =========================================================================== #

def _resolve(client, headers, complaint_id):
    for status, remark in (("in_progress", "Technician assigned."), ("resolved", "Fixed and tested.")):
        response = client.patch(f"{API}/staff/complaints/{complaint_id}/status", headers=headers,
                                json={"status": status, "remark": remark})
        assert response.status_code == 200, response.text


def test_staff_progress_shows_in_the_hostel_feed_and_status_filter(client, world, hdr, departments):
    complaint = report(client, hdr["alice"], departments["hostel"].id, floor_id=world["floors"]["A1"].id)
    other = report(client, hdr["alice"], departments["hostel"].id, "Wing A tap leaking", floor_id=world["floors"]["A1"].id)
    assert {item["status"] for item in client.get(HOSTEL_FEED, headers=hdr["carol"]).json()} == {"submitted"}

    _resolve(client, hdr["hostel_staff"], complaint["id"])
    for viewer in ("alice", "bob", "carol", "hostel_staff", "admin"):
        resolved = client.get(f"{HOSTEL_FEED}?status=resolved", headers=hdr[viewer])
        assert ids(resolved) == {complaint["id"]}
        assert ids(client.get(f"{HOSTEL_FEED}?status=submitted", headers=hdr[viewer])) == {other["id"]}
    assert ids(client.get(f"{HOSTEL_FEED}?status=resolved", headers=hdr["nh"])) == set()


def test_hostel_resolution_metrics_count_each_resolved_complaint_under_its_hostel(
    client, db, world, people, hdr, departments, monkeypatch,
):
    in_main = report(client, hdr["alice"], departments["hostel"].id, floor_id=world["floors"]["A1"].id)
    in_new = report(client, hdr["nh"], departments["hostel"].id, "Wing N tap leaking", floor_id=world["floors"]["N1"].id)
    # Existing unlocated complaints still contribute to historical metrics; only
    # create one using an explicit legacy-mode override, not the Model 2 default.
    with monkeypatch.context() as legacy:
        legacy.setattr(settings, "HOSTEL_COMPLAINT_REQUIRES_FLOOR_ID", False)
        unlocated = report(client, hdr["alice"], departments["hostel"].id, "Hostel fan broken")
    still_open = report(client, hdr["alice"], departments["hostel"].id, "Wing A door stuck", floor_id=world["floors"]["A1"].id)
    for complaint in (in_main, in_new, unlocated):
        _resolve(client, hdr["hostel_staff"], complaint["id"])

    metrics = calculate_hostel_resolution_metrics(db)
    rows = {row["hostel_code"]: row for row in metrics["hostels"]}
    assert rows["MH"]["resolved_count"] == 1
    assert rows["NH"]["resolved_count"] == 1
    assert metrics["unlocated"]["resolved_count"] == 1  # counted, not silently dropped
    assert db.query(Complaint).filter(Complaint.id == still_open["id"]).one().resolved_at is None
    for row in (rows["MH"], rows["NH"], metrics["unlocated"]):
        assert row["average_resolution_hours"] is not None and row["average_resolution_hours"] >= 0


# =========================================================================== #
# 8. STAFF AND ADMIN VIEW
# =========================================================================== #

def test_hostel_staff_and_admin_see_both_hostels_and_can_filter_by_one(client, world, hdr, departments):
    main = report(client, hdr["alice"], departments["hostel"].id, floor_id=world["floors"]["A1"].id)
    new = report(client, hdr["nh"], departments["hostel"].id, "Wing N tap leaking", floor_id=world["floors"]["N1"].id)
    for viewer in ("hostel_staff", "admin"):
        assert ids(client.get(HOSTEL_FEED, headers=hdr[viewer])) == {main["id"], new["id"]}
        assert ids(client.get(f"{HOSTEL_FEED}?hostel_id={world['main'].id}", headers=hdr[viewer])) == {main["id"]}
        assert ids(client.get(f"{HOSTEL_FEED}?hostel_id={world['new'].id}", headers=hdr[viewer])) == {new["id"]}
        assert client.get(f"{HOSTEL_FEED}?hostel_id=999999", headers=hdr[viewer]).status_code == 404
    assert client.get(f"{HOSTEL_FEED}?hostel_id={world['main'].id}", headers=hdr["alice"]).status_code == 403
    assert client.get(HOSTEL_FEED, headers=hdr["it_staff"]).status_code == 403


def test_department_feed_is_open_to_every_signed_in_role(client, hdr, departments):
    wide = report(client, hdr["alice"], departments["library"].id, "Library AC not working")
    for viewer in hdr:
        assert ids(client.get(dept_feed(departments["library"].id), headers=hdr[viewer])) == {wide["id"]}, viewer
    assert client.get(dept_feed(departments["library"].id)).status_code == 401
    assert client.get(dept_feed(999999), headers=hdr["alice"]).status_code == 404
