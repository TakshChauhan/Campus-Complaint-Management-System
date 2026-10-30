"""Shared canonical hostel + HMC test world for Sprint 3 feed and duplicate tests.

Main Hostel (MH) has wings A-D, each with floors 1-3. HMC groups:

    AB1  -> A/1, B/1   (Alice lives on A/1)
    C1   -> C/1        (Bob lives on C/1; same floor level as AB1)
    BD2  -> B/2, D/2   (one wing can belong to different groups on different floors)
    BC3  -> B/3, C/3
    unmapped: D/1, A/2, C/2, A/3, D/3

New Hostel (NH) has wing N with floor 1, group N1.
"""
from datetime import datetime, timezone

from app.core.security import create_access_token, get_password_hash
from app.models.hmc_group import HMCGroup, HMCGroupFloor
from app.models.hostel import Hostel
from app.models.hostel_floor import HostelFloor
from app.models.hostel_wing import HostelWing
from app.models.student_residence import StudentResidence
from app.models.user import User

FORBIDDEN_FEED_KEYS = {
    "description", "description_preview", "created_by_id", "reporter_id", "reporter_name",
    "reporter_email", "email", "name", "student_id", "student_name", "student_email",
    "feed_review_note", "remark",
}
FEED_ITEM_KEYS = {"id", "title", "department_id", "department_name", "status", "created_at", "updated_at", "reopen_count"}
HOSTEL_FEED_ITEM_KEYS = FEED_ITEM_KEYS | {"hostel", "wing", "floor"}


def headers_for(user: User) -> dict:
    token = create_access_token(subject=str(user.id), claims={"role": user.role, "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def make_user(db, key: str, role: str, department_id=None) -> User:
    user = User(
        name=f"{role.title()} {key.title()}", email=f"{key}@campus.edu",
        password_hash=get_password_hash("Password123!"), role=role,
        is_active=True, department_id=department_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_residence(db, student: User, floor: HostelFloor, verifier: User | None, status: str = "verified") -> StudentResidence:
    residence = db.query(StudentResidence).filter_by(student_id=student.id).first()
    if residence is None:
        residence = StudentResidence(student_id=student.id, floor_id=floor.id)
        db.add(residence)
    residence.floor_id = floor.id
    residence.status = status
    decided = status != "pending"
    residence.verified_by_id = verifier.id if decided and verifier else None
    residence.verified_at = datetime.now(timezone.utc) if decided else None
    db.commit()
    return residence


def build_world(db, departments, alice: User, bob: User) -> dict:
    hostel_staff = make_user(db, "hostel.staff", "staff", departments["hostel"].id)
    it_staff = make_user(db, "it.staff", "staff", departments["it"].id)

    main = Hostel(code="MH", name="Main Hostel")
    new = Hostel(code="NH", name="New Hostel")
    db.add_all([main, new])
    db.flush()
    wings = {code: HostelWing(hostel_id=main.id, code=code, name=f"Wing {code}") for code in "ABCD"}
    wings["N"] = HostelWing(hostel_id=new.id, code="N", name="Wing N")
    db.add_all(wings.values())
    db.flush()
    floors = {}
    for code, wing in wings.items():
        for level in (("1",) if code == "N" else ("1", "2", "3")):
            floors[f"{code}{level}"] = HostelFloor(wing_id=wing.id, code=level, name=f"Floor {level}")
    db.add_all(floors.values())
    db.flush()

    def group(name, hostel, level, *floor_keys):
        g = HMCGroup(name=name, hostel_id=hostel.id, floor_code=level)
        db.add(g)
        db.flush()
        db.add_all(HMCGroupFloor(hmc_group_id=g.id, floor_id=floors[k].id) for k in floor_keys)
        return g

    groups = {
        "AB1": group("Main Floor 1 HMC AB", main, "1", "A1", "B1"),
        "C1": group("Main Floor 1 HMC C", main, "1", "C1"),
        "BD2": group("Main Floor 2 HMC BD", main, "2", "B2", "D2"),
        "BC3": group("Main Floor 3 HMC BC", main, "3", "B3", "C3"),
        "N1": group("New Floor 1 HMC N", new, "1", "N1"),
    }
    db.commit()
    set_residence(db, alice, floors["A1"], hostel_staff)
    set_residence(db, bob, floors["C1"], hostel_staff)
    return {
        "main": main, "new": new, "wings": wings, "floors": floors, "groups": groups,
        "hostel_staff": hostel_staff, "it_staff": it_staff,
    }


def submit(client, headers, department_id, title, *, is_public=True, description=None, **extra):
    return client.post("/api/v1/complaints", headers=headers, json={
        "title": title,
        "description": description or "A detailed report describing the observed campus issue.",
        "department_id": department_id, "is_public": is_public, **extra,
    })


def feed_ids(response) -> set[int]:
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


def duplicate_ids(client, headers, title, description) -> set[int]:
    response = client.post("/api/v1/complaints/duplicate-suggestions", headers=headers,
                           json={"title": title, "description": description})
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["matches"]}
