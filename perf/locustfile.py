"""S5-36 load tests for the CCMS API (Locust).

Read-only on purpose: no complaint, comment or account is created, so a run
does not fill the staging database with test data. The two POST calls
(duplicate suggestions, department suggestion) only compute and return results.

Never run against production. Tell Taksh before every staging run (Sprint 5 rule).

Profiles (pick one with CCMS_PROFILE, default "smoke"):

    smoke        1 user for 1 minute
    load         20 users for 5 minutes (after a 1-minute ramp)
    progressive  ramp 10 -> 100 users in steps of 10 every 30 seconds
    spike        10 users, jump to 100 for 1 minute, back to 10

Sign-in: the API allows 15 auth requests per minute per IP, and every Locust
user shares one IP. So the run signs in a small pool of student accounts once
(CCMS_ACCOUNTS, at most 10) and every simulated user reuses those tokens.
Passwords come from CCMS_PASSWORD and are never stored in the repo.
"""

from __future__ import annotations

import itertools
import os
import random
import threading

from locust import HttpUser, LoadTestShape, between, events, task
from locust.exception import StopUser

API = "/api/v1"
MAX_ACCOUNTS = 10  # stays under the 15 sign-ins/minute limit

_tokens: list[str] = []
_token_cycle = None
_department_ids: list[int] = []
_lock = threading.Lock()

SAMPLE_TEXT = [
    ("Projector not working", "The projector in lab 3 shows no signal from any laptop."),
    ("Wi-Fi drops in library", "The library Wi-Fi disconnects every few minutes."),
    ("Water leak in washroom", "A tap on the first floor washroom is leaking continuously."),
    ("Mess food quality", "The dinner served yesterday was cold and undercooked."),
]


def _accounts() -> list[str]:
    raw = os.getenv("CCMS_ACCOUNTS", "")
    accounts = [a.strip() for a in raw.split(",") if a.strip()]
    if not accounts:
        raise SystemExit("Set CCMS_ACCOUNTS to a comma-separated list of student emails.")
    if len(accounts) > MAX_ACCOUNTS:
        raise SystemExit(f"Use at most {MAX_ACCOUNTS} accounts (auth rate limit).")
    return accounts


@events.test_start.add_listener
def sign_in_pool(environment, **_kwargs):
    """Sign in each pool account once, before any simulated user starts."""
    global _token_cycle
    password = os.getenv("CCMS_PASSWORD")
    if not password:
        raise SystemExit("Set CCMS_PASSWORD (the pool accounts' password).")

    import requests  # installed with locust

    host = environment.host.rstrip("/")
    for email in _accounts():
        res = requests.post(f"{host}{API}/auth/login", json={"email": email, "password": password}, timeout=60)
        res.raise_for_status()
        _tokens.append(res.json()["access_token"])
    _token_cycle = itertools.cycle(_tokens)

    # /departments needs a signed-in user too.
    res = requests.get(f"{host}{API}/departments", headers={"Authorization": f"Bearer {_tokens[0]}"}, timeout=60)
    res.raise_for_status()
    # Hostel complaints use the restricted hostel feed; the department feed
    # answers 400 "hostel_feed_required" for the Hostel department by design.
    _department_ids.extend(d["id"] for d in res.json() if "hostel" not in d["name"].lower())
    if not _department_ids:
        raise SystemExit("No active departments found; the feed task needs at least one.")


class Student(HttpUser):
    """A student browsing: their complaints, the feed, and the raise-complaint form."""

    wait_time = between(1, 3)

    def on_start(self):
        if not _tokens:
            raise StopUser()
        with _lock:
            token = next(_token_cycle)
        self.client.headers.update({"Authorization": f"Bearer {token}"})

    @task(4)
    def my_complaints(self):
        self.client.get(f"{API}/complaints/mine?limit=20&offset=0", name="GET /complaints/mine")

    @task(3)
    def department_feed(self):
        dept = random.choice(_department_ids)
        self.client.get(f"{API}/feeds/departments/{dept}?limit=20&offset=0", name="GET /feeds/departments/{id}")

    @task(2)
    def departments(self):
        self.client.get(f"{API}/departments", name="GET /departments")

    @task(2)
    def duplicate_suggestions(self):
        title, description = random.choice(SAMPLE_TEXT)
        self.client.post(
            f"{API}/complaints/duplicate-suggestions",
            json={"title": title, "description": description},
            name="POST /complaints/duplicate-suggestions",
        )

    @task(1)
    def suggest_department(self):
        title, description = random.choice(SAMPLE_TEXT)
        self.client.post(
            f"{API}/departments/suggest",
            json={"title": title, "description": description},
            name="POST /departments/suggest",
        )

    @task(1)
    def health(self):
        self.client.get("/health/ready", name="GET /health/ready")


# --- Load profiles -------------------------------------------------------------
# Each stage is (end_second, users, spawn_rate). LoadTestShape drives the run.

PROFILES = {
    "smoke": [(60, 1, 1)],
    "load": [(60, 20, 1), (360, 20, 1)],
    "progressive": [(30 * step, 10 * step, 5) for step in range(1, 11)] + [(330, 100, 5)],
    "spike": [(60, 10, 5), (120, 100, 50), (180, 10, 50)],
}


class ProfileShape(LoadTestShape):
    def __init__(self):
        super().__init__()
        name = os.getenv("CCMS_PROFILE", "smoke")
        if name not in PROFILES:
            raise SystemExit(f"Unknown CCMS_PROFILE {name!r}; choose from {sorted(PROFILES)}.")
        self.stages = PROFILES[name]

    def tick(self):
        elapsed = self.get_run_time()
        for end, users, rate in self.stages:
            if elapsed < end:
                return users, rate
        return None
