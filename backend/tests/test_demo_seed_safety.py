"""Regression checks: demo accounts cannot be created in hosted environments."""

import pytest


def test_demo_seeding_rejected_in_production_even_with_override(monkeypatch):
    from app.core.config import settings
    from app.scripts.seed_dev_users import seed_development_users

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_DEMO_SEEDING", "true")

    # Fail closed before touching the DB, even if an override is configured.
    with pytest.raises(RuntimeError, match="Demo user seeding forbidden"):
        seed_development_users(db=object())


def test_cloud_setup_refuses_demo_seeding_before_connecting(monkeypatch):
    from scripts import migrate_and_seed_cloud as cloud

    def forbidden_connect(*args, **kwargs):
        pytest.fail("Cloud setup must reject demo seeding before opening a DB connection")

    monkeypatch.setattr(cloud, "create_engine", forbidden_connect)
    assert cloud.run_cloud_setup("postgresql+psycopg://invalid:invalid@localhost/unused", seed_demo=True) is False
