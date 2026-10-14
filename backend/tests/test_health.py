def test_health_check_returns_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "project" in data
    assert "environment" in data
    assert "version" in data


def test_openapi_schema_accessible(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema
    assert "/api/v1/auth/register" in schema["paths"]
    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/users/me" in schema["paths"]
    assert "/api/v1/departments" in schema["paths"]
    assert "/api/v1/complaints" in schema["paths"]
    assert "/api/v1/complaints/mine" in schema["paths"]


def test_swagger_ui_accessible(client):
    response = client.get("/docs")
    assert response.status_code == 200


def test_cors_headers_allowed_origin(client):
    """Allowed origin receives Access-Control-Allow-Origin header."""
    headers = {"Origin": "http://localhost:5173"}
    response = client.get("/health", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_headers_unapproved_origin(client):
    """Unapproved origin does not receive Access-Control-Allow-Origin header."""
    headers = {"Origin": "http://malicious-site.example.com"}
    response = client.get("/health", headers=headers)
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_api_security_headers_present(client, student_headers):
    """Standard API responses include X-Content-Type-Options and Referrer-Policy."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("referrer-policy") == "no-referrer"

    # Profile response must also include Cache-Control: no-store
    user_res = client.get("/api/v1/users/me", headers=student_headers)
    assert user_res.status_code == 200
    assert user_res.headers.get("x-content-type-options") == "nosniff"
    assert user_res.headers.get("referrer-policy") == "no-referrer"
    assert "no-store" in user_res.headers.get("cache-control", "")

