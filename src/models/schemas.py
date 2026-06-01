from typing import Optional
from pydantic import BaseModel
from src.core.jobs import JobStatus


class Query(BaseModel):
    prompt: str
    timeout: Optional[float] = None  # sync endpoint only; falls back to settings


class ExecResult(BaseModel):
    code: int
    stdout: str
    stderr: str


class JobCreated(BaseModel):
    job_id: str
    status: JobStatus


class JobStatusOut(BaseModel):
    job_id: str
    status: JobStatus
    code: Optional[int] = None
    output: str
