from fastapi import APIRouter

from . import admin, auth, dashboard, grade, images, lots, me, reports, verify

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(lots.router, prefix="/lots", tags=["lots"])
api_router.include_router(me.router, prefix="/me", tags=["farmer"])
api_router.include_router(images.router, prefix="/images", tags=["images"])
api_router.include_router(grade.router, prefix="/grade", tags=["grade"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(reports.router, prefix="", tags=["reports"])
api_router.include_router(verify.router, prefix="", tags=["verify"])
