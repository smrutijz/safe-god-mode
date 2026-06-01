from fastapi import APIRouter, HTTPException

from src.core.jobs import JobStatus, create_job, get_job_state, run_claude_task
from src.models.schemas import JobCreated, JobStatusOut, Query

router = APIRouter(prefix="/jobs", tags=["async"])


@router.post("", response_model=JobCreated, status_code=202)
def submit(q: Query):
    """ASYNC: enqueue the run in Celery, return a job_id immediately.

    Returns in milliseconds. The Celery worker runs Claude to completion
    regardless of the client connection. Fetch output via GET /jobs/{id}
    (poll) or the websocket stream.
    """
    job_id = create_job(q.prompt)
    run_claude_task.delay(job_id, q.prompt)
    return JobCreated(job_id=job_id, status=JobStatus.pending)


@router.get("/{job_id}", response_model=JobStatusOut)
def get_job(job_id: str):
    """Poll a job's status and accumulated output so far."""
    state = get_job_state(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown job")
    code_str = state.get("code", "")
    return JobStatusOut(
        job_id=job_id,
        status=state["status"],
        code=int(code_str) if code_str else None,
        output="\n".join(state["lines"]),
    )
