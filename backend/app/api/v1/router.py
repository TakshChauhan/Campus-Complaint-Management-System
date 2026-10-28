from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.complaints import router as complaints_router
from app.api.v1.endpoints.departments import router as departments_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.staff import router as staff_router
from app.api.v1.endpoints.staff_residences import router as staff_residences_router
from app.api.v1.endpoints.locations import router as locations_router
from app.api.v1.endpoints.feeds import router as feeds_router
from app.api.v1.endpoints.hmc import router as hmc_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(departments_router)
api_v1_router.include_router(complaints_router)
api_v1_router.include_router(staff_router)
api_v1_router.include_router(staff_residences_router)
api_v1_router.include_router(locations_router)
api_v1_router.include_router(feeds_router)
api_v1_router.include_router(hmc_router)
