# app/api/v1/router.py

from fastapi import APIRouter
from app.api.v1 import auth, jobs, uploads
from app.api.v1.endpoints import signing, audit, sharing, correlations

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(jobs.router)
api_router.include_router(uploads.router)
api_router.include_router(signing.router)
api_router.include_router(audit.router)
api_router.include_router(sharing.router)
api_router.include_router(correlations.router, tags=["correlations"])