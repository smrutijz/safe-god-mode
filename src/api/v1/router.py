from fastapi import APIRouter

from src.api.v1 import execute, jobs, stream

api_router = APIRouter()
api_router.include_router(execute.router)
api_router.include_router(jobs.router)
api_router.include_router(stream.router)
