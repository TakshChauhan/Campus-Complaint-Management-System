import logging
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.db.session import engine

# Configure structured logging with secret-safe redaction for OAuth callback queries
class SensitiveQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for secret_param in ("code=", "state="):
                if secret_param in record.msg:
                    record.msg = record.msg.split("?")[0] + " [QUERY_PARAMS_REDACTED]"
        if hasattr(record, "args") and isinstance(record.args, tuple):
            new_args = []
            for arg in record.args:
                if isinstance(arg, str) and ("code=" in arg or "state=" in arg):
                    new_args.append(arg.split("?")[0] + " [QUERY_PARAMS_REDACTED]")
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)
        return True

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
query_filter = SensitiveQueryFilter()
logging.getLogger().addFilter(query_filter)
logging.getLogger("uvicorn.access").addFilter(query_filter)
logger = logging.getLogger("ccms.backend")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Campus Complaint Management System (CCMS) REST API - Sprint 1 Backend Foundation. "
        "Provides role-based authentication, student grievance lodging, active department catalog, "
        "and automated keyword-based advisory department suggestion."
    ),
    docs_url="/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None,
)

# CORS configuration hardened for Sprint 1.
# The SPA authenticates with an Authorization bearer header (never cookies), so
# credentialed CORS is unnecessary. Only the methods Sprint 1 actually uses are
# allowed, and X-Total-Count is exposed for complaint-history pagination.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS", "HEAD"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=["X-Total-Count"],
    max_age=600,
)


# Security headers middleware for API defense-in-depth
@app.middleware("http")
async def add_api_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"

    # For sensitive authentication and profile endpoints, disable client/intermediate caching
    path = request.url.path
    if path.startswith(f"{settings.API_V1_STR}/auth") or path == f"{settings.API_V1_STR}/users/me":
        response.headers["Cache-Control"] = "no-store"

    return response


# Exception Handlers for consistent structured JSON errors
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Format validation errors cleanly for frontend consumption
    clean_errors = []
    for err in exc.errors():
        field_loc = " -> ".join(str(loc) for loc in err.get("loc", []))
        clean_errors.append({
            "field": field_loc,
            "message": err.get("msg"),
            "type": err.get("type"),
        })

    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, clean_errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": clean_errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. Please try again later."},
    )


def _database_reachable() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        # Log only the exception type: driver messages can include host names.
        logger.warning("Database connectivity check failed (%s)", type(exc).__name__)
        return False


# Liveness / health endpoint (always HTTP 200 so a slow DB does not restart the container)
@app.get(
    "/health",
    tags=["System"],
    summary="Health check endpoint",
    description="Reports API liveness and database connectivity. Returns HTTP 200 with status 'degraded' when the database is unreachable.",
    response_model=Dict[str, Any],
)
def health_check() -> Dict[str, Any]:
    db_status = "operational" if _database_reachable() else "unavailable"
    return {
        "status": "healthy" if db_status == "operational" else "degraded",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
    }


# Readiness endpoint: 503 until the database answers, for load balancers and the admin dashboard
@app.get(
    "/health/ready",
    tags=["System"],
    summary="Readiness check",
    description="Returns HTTP 200 when the API can serve requests that need the database, otherwise HTTP 503.",
    response_model=Dict[str, Any],
    responses={503: {"description": "Database is not reachable"}},
)
def readiness_check() -> JSONResponse:
    ready = _database_reachable()
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"ready": ready, "database": "operational" if ready else "unavailable"},
        headers={"Cache-Control": "no-store"},
    )


from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if not settings.ENABLE_API_DOCS:
        return None
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    if "ValidationError" in openapi_schema.get("components", {}).get("schemas", {}):
        openapi_schema["components"]["schemas"]["ValidationError"] = {
            "title": "ValidationError",
            "type": "object",
            "properties": {
                "field": {"title": "Field", "type": "string"},
                "message": {"title": "Message", "type": "string"},
                "type": {"title": "Error Type", "type": "string"},
            },
            "required": ["field", "message", "type"],
        }
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Include versioned API router under /api/v1
app.include_router(api_v1_router, prefix=settings.API_V1_STR)
