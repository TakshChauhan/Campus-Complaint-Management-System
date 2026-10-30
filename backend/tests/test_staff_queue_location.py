"""S3-24: hostel filter and location fields on the staff complaint queue."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.complaint import Complaint
from sprint3_hmc_world import build_world, headers_for

QUEUE = "/api/v1/staff/complaints"
BASE = datetime(2026, 10, 20, tzinfo=timezone.utc)


@pytest.fixture
def world(db, seeded_departments, student_user, student_b_user):
    return build_world(db, seeded_departments, student_user, student_b_user)


def _complaint(db, *, department_id, created_by_id, title, minutes, floor=None, wing=None, hostel=None, legacy=None):
    complaint = Complaint(
        title=title,
        description="The corridor lights have not worked for two days.",
        department_id=department_id,
        created_by_id=created_by_id,
        status="submitted",
        is_public=False,
        floor_id=floor.id if floor else None,
        hostel=hostel.name if hostel else legacy,
        wing=wing.name if wing else None,
        floor=floor.name if floor else None,
        created_at=BASE + timedelta(minutes=minutes),
        updated_at=BASE + timedelta(minutes=minutes),
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint


@pytest.fixture
def queue(db, world, seeded_departments, student_user):
    hostel_dept = seeded_departments["hostel"].id
    it_dept = seeded_departments["it"].id
    main, new = world["main"], world["new"]
    wings, floors = world["wings"], world["floors"]

    def seed(title, minutes, department_id=hostel_dept, **location):
        return _complaint(
            db, department_id=department_id, created_by_id=student_user.id, title=title, minutes=minutes, **location
        )

    return {
        "main_a1": seed("Main A1", 1, hostel=main, wing=wings["A"], floor=floors["A1"]),
        "main_b2": seed("Main B2", 2, hostel=main, wing=wings["B"], floor=floors["B2"]),
        "new_n1": seed("New N1", 3, hostel=new, wing=wings["N"], floor=floors["N1"]),
        "legacy": seed("Legacy text only", 4, legacy="Main Hostel"),
        "it_main_a1": seed("IT on Main A1", 5, department_id=it_dept, hostel=main, wing=wings["A"], floor=floors["A1"]),
    }


def test_hostel_filter_returns_only_that_hostels_department_complaints(client, world, queue):
    response = client.get(f"{QUEUE}?hostel_id={world['main'].id}", headers=headers_for(world["hostel_staff"]))

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Main B2", "Main A1"]
    assert response.headers["X-Total-Count"] == "2"


def test_hostel_filter_total_counts_filtered_rows_not_page(client, world, queue):
    response = client.get(
        f"{QUEUE}?hostel_id={world['main'].id}&limit=1", headers=headers_for(world["hostel_staff"])
    )

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Main B2"]
    assert response.headers["X-Total-Count"] == "2"


def test_hostel_filter_keeps_department_scoping(client, world, queue):
    response = client.get(f"{QUEUE}?hostel_id={world['main'].id}", headers=headers_for(world["it_staff"]))

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["IT on Main A1"]
    assert response.headers["X-Total-Count"] == "1"


def test_no_hostel_filter_returns_all_department_complaints(client, world, queue):
    response = client.get(QUEUE, headers=headers_for(world["hostel_staff"]))

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Legacy text only", "New N1", "Main B2", "Main A1"]
    assert response.headers["X-Total-Count"] == "4"


def test_queue_items_include_location_fields(client, world, queue):
    response = client.get(QUEUE, headers=headers_for(world["hostel_staff"]))
    items = {item["title"]: item for item in response.json()}

    assert items["Main A1"]["floor_id"] == world["floors"]["A1"].id
    assert (items["Main A1"]["hostel"], items["Main A1"]["wing"], items["Main A1"]["floor"]) == (
        "Main Hostel",
        "Wing A",
        "Floor 1",
    )
    assert items["Legacy text only"]["floor_id"] is None
    assert items["Legacy text only"]["hostel"] == "Main Hostel"
    assert items["Legacy text only"]["wing"] is None
    assert items["Legacy text only"]["floor"] is None


def test_queue_location_matches_detail_view(client, world, queue):
    headers = headers_for(world["hostel_staff"])
    item = next(i for i in client.get(QUEUE, headers=headers).json() if i["title"] == "New N1")
    detail = client.get(f"{QUEUE}/{item['id']}", headers=headers).json()

    assert (item["hostel"], item["wing"], item["floor"]) == (detail["hostel"], detail["wing"], detail["floor"])


def test_unknown_hostel_returns_empty_list(client, world, queue):
    response = client.get(f"{QUEUE}?hostel_id=999999", headers=headers_for(world["hostel_staff"]))

    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["X-Total-Count"] == "0"


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_invalid_hostel_id_is_rejected(client, world, value):
    response = client.get(f"{QUEUE}?hostel_id={value}", headers=headers_for(world["hostel_staff"]))

    assert response.status_code == 422
