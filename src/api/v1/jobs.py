import asyncio

from fastapi import APIRouter, HTTPException

from src.core.jobs import run_job, store
from src.models.schemas import JobCreated, JobStatusOut, Query

router = APIRouter(prefix="/jobs", tags=["async"])


@router.post("", response_model=JobCreated, status_code=202)
async def submit(q: Query):
    """ASYNC: start the run in the background, return a job_id immediately.

    Returns in milliseconds, so it never hits the 15-min gate. The job runs to
    completion regardless of the client. Fetch output via GET /jobs/{id} (poll)
    or the websocket stream.
    """
    job = store.create(q.prompt)
    asyncio.create_task(run_job(job))
    return JobCreated(job_id=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobStatusOut)
async def get_job(job_id: str):
    """Poll a job's status and accumulated output so far."""
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return JobStatusOut(
        job_id=job.id,
        status=job.status,
        code=job.code,
        output="\n".join(job.lines),
    )
