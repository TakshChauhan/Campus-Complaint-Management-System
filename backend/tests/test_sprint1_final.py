"""Tests for Sprint 1 final enhancements.

Covers: registration does not issue a session, complaint-history search /
filters / total count, owner-only complaint detail, complaint retention on
user deletion, readiness endpoint, CORS exposure, Google domain policy and
migration 0004 data preservation.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.complaint import Complaint
from app.models.user import User


def _file(client, headers, dept_id, title, description="A sufficiently long description of the issue."):
    res = client.post(
        "/api/v1/complaints",
        json={"title": title, "description": description, "department_id": dept_id},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- registration

def test_registration_returns_profile_without_token(client):
    res = client.post(
        "/api/v1/auth/register",
        json={"name": "New Student", "email": "202499999@dau.ac.in", "password": "LongEnough123"},
    )
    assert res.status_code == 201
    body = res.json()
    assert "access_token" not in body
    assert body["email_verified"] is False
    assert body["role"] == "student"


def test_registered_user_must_login_explicitly(client, mock_verification_email_sender):
    client.post(
        "/api/v1/auth/register",
        json={"name": "New Student", "email": "202499998@dau.ac.in", "password": "LongEnough123"},
    )
    # No implicit session: profile requires a token.
    assert client.get("/api/v1/users/me").status_code == 401
    login = client.post(
        "/api/v1/auth/login", json={"email": "202499998@dau.ac.in", "password": "LongEnough123"}
    )
    assert login.status_code == 403  # new student must verify email first
    assert len(mock_verification_email_sender.sent_emails) == 1
    token = mock_verification_email_sender.sent_emails[0]["token"]
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    login = client.post(
        "/api/v1/auth/login", json={"email": "202499998@dau.ac.in", "password": "LongEnough123"}
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "student"


# --------------------------------------------------------------------------- history

def test_history_total_count_header_and_cors_exposure(client, student_headers, seeded_departments):
    for i in range(3):
        _file(client, student_headers, seeded_departments["it"].id, f"Wi-Fi outage number {i}")
    res = client.get(
        "/api/v1/complaints/mine?limit=2&offset=0",
        headers={**student_headers, "Origin": "http://localhost:5173"},
    )
    assert res.status_code == 200
    assert len(res.json()) == 2
    assert res.headers["x-total-count"] == "3"
    assert "x-total-count" in res.headers.get("access-control-expose-headers", "").lower()


def test_history_search_covers_all_pages(client, student_headers, seeded_departments):
    target = _file(client, student_headers, seeded_departments["hostel"].id, "Leaking tap in hostel block B")
    for i in range(5):
        _file(client, student_headers, seeded_departments["it"].id, f"Network issue {i}")
    # Target is the oldest -> it would not be on the first page of 2 without server-side search.
    res = client.get("/api/v1/complaints/mine?limit=2&q=leaking", headers=student_headers)
    assert res.status_code == 200
    assert [c["id"] for c in res.json()] == [target["id"]]
    assert res.headers["x-total-count"] == "1"


def test_history_search_by_reference(client, student_headers, seeded_departments):
    first = _file(client, student_headers, seeded_departments["it"].id, "Projector broken")
    _file(client, student_headers, seeded_departments["it"].id, "Printer broken")
    for q in (f"CMP-{first['id']}", f"cmp{first['id']}", str(first["id"])):
        res = client.get("/api/v1/complaints/mine", params={"q": q}, headers=student_headers)
        assert first["id"] in [c["id"] for c in res.json()], q


def test_history_search_treats_wildcards_literally(client, student_headers, seeded_departments):
    _file(client, student_headers, seeded_departments["it"].id, "Plain title here")
    res = client.get("/api/v1/complaints/mine", params={"q": "%"}, headers=student_headers)
    assert res.status_code == 200
    assert res.json() == []


def test_history_department_filter_and_sort(client, student_headers, seeded_departments):
    a = _file(client, student_headers, seeded_departments["it"].id, "Router down first")
    _file(client, student_headers, seeded_departments["library"].id, "Book missing")
    b = _file(client, student_headers, seeded_departments["it"].id, "Router down second")
    dept = seeded_departments["it"].id
    newest = client.get(f"/api/v1/complaints/mine?department_id={dept}", headers=student_headers).json()
    oldest = client.get(
        f"/api/v1/complaints/mine?department_id={dept}&sort=oldest", headers=student_headers
    ).json()
    assert [c["id"] for c in newest] == [b["id"], a["id"]]
    assert [c["id"] for c in oldest] == [a["id"], b["id"]]
    assert all(c["department_id"] == dept for c in newest)
    assert newest[0]["description_preview"]


def test_history_date_filter(client, db, student_headers, student_user, seeded_departments):
    old = _file(client, student_headers, seeded_departments["it"].id, "Old complaint")
    row = db.get(Complaint, old["id"])
    row.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    db.commit()
    recent = _file(client, student_headers, seeded_departments["it"].id, "Recent complaint")
    today = datetime.now(timezone.utc).date().isoformat()
    res = client.get(f"/api/v1/complaints/mine?date_from={today}", headers=student_headers).json()
    assert [c["id"] for c in res] == [recent["id"]]
    bad = client.get(
        "/api/v1/complaints/mine?date_from=2026-02-01&date_to=2026-01-01", headers=student_headers
    )
    assert bad.status_code == 422


def test_history_invalid_sort_rejected(client, student_headers):
    assert client.get("/api/v1/complaints/mine?sort=random", headers=student_headers).status_code == 422


def test_history_search_isolated_to_owner(client, student_headers, student_b_headers, seeded_departments):
    _file(client, student_b_headers, seeded_departments["it"].id, "Bob secret wifi complaint")
    res = client.get("/api/v1/complaints/mine?q=secret", headers=student_headers)
    assert res.json() == []
    assert res.headers["x-total-count"] == "0"


# --------------------------------------------------------------------------- detail

def test_complaint_detail_owner_only(client, student_headers, student_b_headers, seeded_departments):
    mine = _file(client, student_headers, seeded_departments["hostel"].id, "Fan not working in room")
    ok = client.get(f"/api/v1/complaints/{mine['id']}", headers=student_headers)
    assert ok.status_code == 200
    assert ok.json()["description"].startswith("A sufficiently long")
    assert client.get(f"/api/v1/complaints/{mine['id']}", headers=student_b_headers).status_code == 404
    assert client.get("/api/v1/complaints/999999", headers=student_headers).status_code == 404
    assert client.get(f"/api/v1/complaints/{mine['id']}").status_code == 401


def test_complaint_detail_forbidden_for_staff_and_admin(client, staff_headers, admin_headers):
    assert client.get("/api/v1/complaints/1", headers=staff_headers).status_code == 403
    assert client.get("/api/v1/complaints/1", headers=admin_headers).status_code == 403


# --------------------------------------------------------------------------- integrity

def test_orm_user_delete_never_cascades_to_complaints(db, student_user, seeded_departments):
    """ORM layer must not cascade-delete (or null out) a user's complaints.

    The test SQLite engine does not enforce foreign keys, so this isolates the
    ORM behaviour; database-level RESTRICT is verified by the migration test.
    """
    complaint = Complaint(
        title="Retained", description="Must survive user deletion attempts.",
        department_id=seeded_departments["it"].id, created_by_id=student_user.id,
    )
    db.add(complaint)
    db.commit()
    cid, uid = complaint.id, student_user.id
    db.delete(student_user)
    db.commit()
    db.expire_all()
    kept = db.get(Complaint, cid)
    assert kept is not None
    assert kept.created_by_id == uid


def test_model_metadata_declares_restrict():
    fk = next(iter(Complaint.__table__.c.created_by_id.foreign_keys))
    assert fk.ondelete == "RESTRICT"


# --------------------------------------------------------------------------- health

def test_readiness_endpoint_ok(client):
    res = client.get("/health/ready")
    assert res.status_code == 200
    assert res.json() == {"ready": True, "database": "operational"}


def test_readiness_endpoint_reports_unavailable_database(client, monkeypatch):
    import app.main as main_module
    monkeypatch.setattr(main_module, "_database_reachable", lambda: False)
    res = client.get("/health/ready")
    assert res.status_code == 503
    assert res.json()["ready"] is False
    health = client.get("/health").json()
    assert health["status"] == "degraded"
    assert health["database"] == "unavailable"


def test_cors_does_not_allow_credentials(client):
    res = client.options(
        "/api/v1/auth/login",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert res.headers.get("access-control-allow-credentials") is None


# --------------------------------------------------------------------------- google policy

def test_google_new_account_requires_institutional_domain_without_hd_allowlist(db, monkeypatch):
    from app.services.google_auth_service import resolve_or_create_user_for_google
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_HOSTED_DOMAINS", [])
    monkeypatch.setattr(settings, "ALLOWED_EMAIL_DOMAINS", ["dau.ac.in"])
    with pytest.raises(ValueError, match="official university accounts"):
        resolve_or_create_user_for_google(db, sub="g-1", email="someone@gmail.com", name="Some One")
    user, created = resolve_or_create_user_for_google(db, sub="g-2", email="202401000@dau.ac.in", name="Real Student")
    assert created and user.role == "student" and user.email_verified is True


# --------------------------------------------------------------------------- migration 0004

def _cfg(url):
    here = os.path.dirname(__file__)
    cfg = Config(os.path.abspath(os.path.join(here, "..", "alembic.ini")))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", os.path.abspath(os.path.join(here, "..", "alembic")))
    return cfg


def test_migration_0004_preserves_rows_and_restricts_user_delete(tmp_path):
    url = f"sqlite:///{tmp_path / 'm4.db'}"
    cfg = _cfg(url)
    command.upgrade(cfg, "0003_google_oauth_verified_email")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO departments (id, name, is_active) VALUES (1, 'IT Services', 1)"))
        conn.execute(text(
            "INSERT INTO users (id, name, email, password_hash, role, is_active, email_verified) "
            "VALUES (1, 'S', 's@dau.ac.in', 'x', 'student', 1, 0)"
        ))
        conn.execute(text(
            "INSERT INTO complaints (id, title, description, department_id, created_by_id, status) "
            "VALUES (7, 'Kept', 'Existing complaint row', 1, 1, 'submitted')"
        ))

    command.upgrade(cfg, "head")

    fks = inspect(engine).get_foreign_keys("complaints")
    creator_fk = [fk for fk in fks if fk["constrained_columns"] == ["created_by_id"]][0]
    assert creator_fk["options"].get("ondelete") == "RESTRICT"

    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        assert conn.execute(text("SELECT title FROM complaints WHERE id = 7")).scalar() == "Kept"
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM users WHERE id = 1"))
        conn.rollback()
        assert conn.execute(text("SELECT count(*) FROM complaints")).scalar() == 1

    command.downgrade(cfg, "0003_google_oauth_verified_email")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM complaints")).scalar() == 1
    engine.dispose()


# --------------------------------------------------------------------------- production config

def _prod_kwargs(**over):
    base = dict(
        ENVIRONMENT="production",
        DEBUG=False,
        JWT_SECRET="x" * 48,
        DATABASE_URL="postgresql+psycopg://u:p@db.example.supabase.co:5432/postgres?sslmode=require",
        CORS_ORIGINS="https://ccms.example.edu",
        ALLOW_DEMO_SEEDING=False,
        EMAIL_PROVIDER="resend",
    )
    base.update(over)
    return base


def test_production_settings_accept_valid_configuration():
    from app.core.config import Settings
    s = Settings(_env_file=None, **_prod_kwargs())
    assert s.ENABLE_API_DOCS is False
    assert s.CORS_ORIGINS == ["https://ccms.example.edu"]


def test_default_email_domains_are_real_dau_domains():
    from app.core.config import Settings
    assert Settings.model_fields["ALLOWED_EMAIL_DOMAINS"].default == ["dau.ac.in", "daiict.ac.in"]


def test_production_rejects_localhost_cors():
    from app.core.config import Settings
    with pytest.raises(ValueError, match="localhost"):
        Settings(_env_file=None, **_prod_kwargs(CORS_ORIGINS="http://localhost:5173"))


def test_production_rejects_http_google_redirect():
    from app.core.config import Settings
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(_env_file=None, **_prod_kwargs(
            GOOGLE_AUTH_ENABLED=True,
            GOOGLE_OAUTH_CLIENT_ID="id.apps.googleusercontent.com",
            GOOGLE_OAUTH_CLIENT_SECRET="secret",
            GOOGLE_OAUTH_REDIRECT_URI="http://api.example.edu/api/v1/auth/google/callback",
        ))
