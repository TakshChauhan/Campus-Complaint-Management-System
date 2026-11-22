"""CORS must allow every HTTP method the API actually serves.

Found by the S5-35 GUI tests: the admin "Save assignments" button sends
PUT /api/v1/admin/staff/{id}/hostels, but CORS only allowed GET, POST, PATCH,
OPTIONS and HEAD. The browser's preflight got 400, so the request never
reached the API whenever the SPA and API are on different origins (local
dev on two ports, and Vercel + Render). Unit tests call the API directly and
frontend tests mock it, so neither noticed.
"""

import pytest

from app.main import app

ORIGIN = "http://localhost:5173"


def _served_methods() -> set[str]:
    # Read from the OpenAPI schema: it lists every mounted route, however the
    # routers are nested, without depending on FastAPI's internal route types.
    methods: set[str] = set()
    for path, operations in app.openapi()["paths"].items():
        if path.startswith("/api/"):
            methods |= {verb.upper() for verb in operations}
    return methods - {"HEAD", "OPTIONS"}


def test_api_serves_put():
    # Guards the parametrised test below against silently testing nothing.
    assert "PUT" in _served_methods()


@pytest.mark.parametrize("method", sorted(_served_methods()))
def test_preflight_allows_every_served_method(client, method):
    res = client.options(
        "/api/v1/admin/staff/1/hostels",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert res.status_code == 200, f"CORS preflight rejected {method}"
    assert method in res.headers.get("access-control-allow-methods", "")
