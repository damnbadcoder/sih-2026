from fastapi import APIRouter

from app.api.v1 import auth, jobs, transformations, uploads

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(jobs.router)
api_router.include_router(uploads.router)
api_router.include_router(transformations.router)