"""S4-08: PostgreSQL concurrency test for staff complaint status updates.

Two staff members updating the same complaint's status at the same time must
produce exactly one success and one 409 Conflict, with exactly one history row.
SQLite cannot prove this (it serialises writers), so the tests run only against a
dedicated, empty, local PostgreSQL database named by CCMS_DISPOSABLE_TEST_POSTGRES_URL
(the same guard as the migration tests) and are skipped otherwise.

Run locally:

    CCMS_DISPOSABLE_TEST_POSTGRES_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ccms_test \
        pytest -q tests/test_postgresql_concurrency.py

How the race is forced
----------------------
The service reads the complaint, checks the transition, then does a conditional
``UPDATE ... WHERE status = <status it read>``. In the deterministic test a barrier
holds both requests at the moment just before that UPDATE, so both have already read
the old status. PostgreSQL then lets one UPDATE through; the other blocks on the row
lock until the first commits, re-checks the WHERE clause, matches no row and the
service returns 409 "Complaint changed". Because the loser read the old status, this
is the atomic guard being exercised, not the earlier "invalid transition" check.
"""

import os
import threading
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, get_password_hash
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.complaint import Complaint
from app.models.complaint_status_history import ComplaintStatusHistory
from app.models.department import Department
from app.models.user import User

pytestmark = pytest.mark.skipif(
    not os.getenv("CCMS_DISPOSABLE_TEST_POSTGRES_URL"),
    reason="Set CCMS_DISPOSABLE_TEST_POSTGRES_URL to a dedicated, empty, local PostgreSQL test database",
)

BARRIER_TIMEOUT_SECONDS = 15
STAFF_PASSWORD = "Password123!"


@pytest.fixture(scope="module")
def pg_engine():
    """Engine on the disposable PostgreSQL database with the full schema created and removed."""
    from test_migration_0007_complaint_lifecycle import _disposable_postgres_url_problem, _user_tables

    url = os.environ["CCMS_DISPOSABLE_TEST_POSTGRES_URL"]
    problem = _disposable_postgres_url_problem(url)
    if problem:
        pytest.fail(f"Refusing to use CCMS_DISPOSABLE_TEST_POSTGRES_URL: {problem}")

    engine = create_engine(url, pool_size=10, max_overflow=10)
    if _user_tables(engine):
        engine.dispose()
        pytest.fail("Refusing to modify a populated database; CCMS_DISPOSABLE_TEST_POSTGRES_URL must be empty.")

    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        # Leave the database empty so the migration tests that share it can run afterwards.
        engine.dispose()
        cleanup = create_engine(url)
        try:
            Base.metadata.drop_all(bind=cleanup)
        finally:
            cleanup.dispose()


@pytest.fixture
def pg_session_factory(pg_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)


@pytest.fixture
def api(pg_session_factory):
    """Point the app at PostgreSQL with one fresh session per request, like production get_db."""

    def override_get_db():
        session = pg_session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def world(pg_session_factory):
    """One department, a reporting student and several staff; everything is removed afterwards."""
    suffix = f"{os.getpid()}{threading.get_ident()}"
    session = pg_session_factory()
    try:
        department = Department(name=f"IT Services {suffix}", description="Concurrency test", is_active=True)
        student = User(
            name="Concurrency Student", email=f"student.{suffix}@student.campus.edu",
            password_hash=get_password_hash(STAFF_PASSWORD), role="student", is_active=True,
        )
        session.add_all([department, student])
        session.flush()
        staff = [
            User(
                name=f"Staff {index}", email=f"staff{index}.{suffix}@campus.edu",
                password_hash=get_password_hash(STAFF_PASSWORD), role="staff", is_active=True,
                department_id=department.id,
            )
            for index in range(6)
        ]
        session.add_all(staff)
        session.commit()
        ids = {"department": department.id, "student": student.id, "staff": [s.id for s in staff]}
        staff_headers = [
            {"Authorization": "Bearer " + create_access_token(
                subject=str(s.id), claims={"role": "staff", "email": s.email})}
            for s in staff
        ]
    finally:
        session.close()

    yield {**ids, "headers": staff_headers, "factory": pg_session_factory}

    cleanup = pg_session_factory()
    try:
        complaint_ids = cleanup.scalars(
            select(Complaint.id).where(Complaint.department_id == ids["department"])
        ).all()
        if complaint_ids:
            cleanup.query(ComplaintStatusHistory).filter(
                ComplaintStatusHistory.complaint_id.in_(complaint_ids)
            ).delete(synchronize_session=False)
            cleanup.query(Complaint).filter(Complaint.id.in_(complaint_ids)).delete(synchronize_session=False)
        cleanup.query(User).filter(User.id.in_([*ids["staff"], ids["student"]])).delete(synchronize_session=False)
        cleanup.query(Department).filter(Department.id == ids["department"]).delete(synchronize_session=False)
        cleanup.commit()
    finally:
        cleanup.close()


def _make_complaint(world: dict, status: str) -> int:
    session = world["factory"]()
    try:
        now = datetime.now(timezone.utc)
        complaint = Complaint(
            title="Wi-Fi down in the common room",
            description="The connection has been unavailable in the common room since this morning.",
            department_id=world["department"], created_by_id=world["student"], status=status,
            is_public=False, resolved_at=now if status == "resolved" else None,
        )
        session.add(complaint)
        session.commit()
        return complaint.id
    finally:
        session.close()


def _patch_status(complaint_id: int, headers: dict, target: str, remark: str):
    # One TestClient per thread: no shared event loop or portal between concurrent requests.
    with TestClient(app) as client:
        return client.patch(
            f"/api/v1/staff/complaints/{complaint_id}/status",
            headers=headers, json={"status": target, "remark": remark},
        )


def _run_concurrently(jobs: list) -> list:
    """Run each zero-argument job in its own thread; return their results in order."""
    results: list = [None] * len(jobs)
    errors: list = []

    def runner(position: int, job) -> None:
        try:
            results[position] = job()
        except BaseException as exc:  # noqa: BLE001 - surfaced to the test below
            errors.append((position, exc))

    threads = [threading.Thread(target=runner, args=(i, job)) for i, job in enumerate(jobs)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a request thread never finished (deadlock?)"
    assert not errors, f"request threads raised: {errors}"
    return results


def _complaint_state(world: dict, complaint_id: int):
    session = world["factory"]()
    try:
        complaint = session.get(Complaint, complaint_id)
        history = (
            session.query(ComplaintStatusHistory)
            .filter(ComplaintStatusHistory.complaint_id == complaint_id)
            .order_by(ComplaintStatusHistory.id)
            .all()
        )
        return (
            (complaint.status, complaint.resolved_at),
            [(h.from_status, h.to_status, h.actor_id, h.remark) for h in history],
        )
    finally:
        session.close()


@pytest.mark.parametrize(
    "start_status, target_status",
    [("submitted", "in_progress"), ("in_progress", "resolved"), ("reopened", "in_progress")],
)
def test_postgresql_two_staff_same_status_update_gives_one_200_and_one_409(
    api, pg_engine, world, start_status, target_status,
):
    """Both staff have read the old status before either writes; exactly one wins."""
    complaint_id = _make_complaint(world, start_status)
    both_ready = threading.Barrier(2, timeout=BARRIER_TIMEOUT_SECONDS)

    def hold_before_status_update(conn, cursor, statement, parameters, context, executemany):
        # Only the status UPDATE; the reads and the history INSERT are untouched.
        if statement.lstrip().upper().startswith("UPDATE COMPLAINTS"):
            both_ready.wait()

    event.listen(pg_engine, "before_cursor_execute", hold_before_status_update)

    def job(position: int):
        def run():
            return _patch_status(complaint_id, world["headers"][position], target_status, f"staff {position} update")
        return run

    try:
        responses = _run_concurrently([job(0), job(1)])
    finally:
        event.remove(pg_engine, "before_cursor_execute", hold_before_status_update)

    codes = sorted(response.status_code for response in responses)
    assert codes == [200, 409], [(r.status_code, r.text) for r in responses]

    winner_position = next(i for i, r in enumerate(responses) if r.status_code == 200)
    loser = next(r for r in responses if r.status_code == 409)
    # The loser had already read the old status, so the conditional UPDATE is what stopped it.
    assert loser.json()["detail"] == "Complaint changed. Refresh and try again."
    assert responses[winner_position].json()["status"] == target_status

    (final_status, resolved_at), history = _complaint_state(world, complaint_id)
    assert final_status == target_status
    assert (resolved_at is not None) == (target_status == "resolved")
    # Exactly one history row, written by the winner; the loser wrote nothing.
    assert history == [
        (start_status, target_status, world["staff"][winner_position], f"staff {winner_position} update")
    ]


def test_postgresql_many_staff_racing_on_one_complaint_give_exactly_one_success(api, world):
    """Six staff fire the same update together: one 200, five 409, one history row."""
    complaint_id = _make_complaint(world, "submitted")
    start_together = threading.Barrier(6, timeout=BARRIER_TIMEOUT_SECONDS)

    def job(position: int):
        def run():
            start_together.wait()
            return _patch_status(complaint_id, world["headers"][position], "in_progress", f"staff {position}")
        return run

    responses = _run_concurrently([job(i) for i in range(6)])

    codes = [response.status_code for response in responses]
    assert codes.count(200) == 1 and codes.count(409) == 5, [(r.status_code, r.text) for r in responses]

    winner_position = codes.index(200)
    (final_status, _), history = _complaint_state(world, complaint_id)
    assert final_status == "in_progress"
    assert history == [("submitted", "in_progress", world["staff"][winner_position], f"staff {winner_position}")]


def test_postgresql_racing_updates_on_different_complaints_both_succeed(api, world):
    """Row-level conflict only: two staff on two different complaints must not block or fail each other."""
    first, second = _make_complaint(world, "submitted"), _make_complaint(world, "submitted")
    start_together = threading.Barrier(2, timeout=BARRIER_TIMEOUT_SECONDS)

    def job(position: int, complaint_id: int):
        def run():
            start_together.wait()
            return _patch_status(complaint_id, world["headers"][position], "in_progress", f"staff {position}")
        return run

    responses = _run_concurrently([job(0, first), job(1, second)])

    assert [response.status_code for response in responses] == [200, 200], [r.text for r in responses]
    for position, complaint_id in enumerate((first, second)):
        (final_status, _), history = _complaint_state(world, complaint_id)
        assert final_status == "in_progress"
        assert history == [("submitted", "in_progress", world["staff"][position], f"staff {position}")]
