import asyncio
import shlex
import uuid
from enum import Enum
from typing import Optional

import asyncssh

from src.core.config import settings
from src.core.iap import iap_ssh


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"


class Job:
    """A single Claude Code run plus a fan-out buffer for streaming."""

    def __init__(self, prompt: str):
        self.id: str = uuid.uuid4().hex
        self.prompt: str = prompt
        self.status: JobStatus = JobStatus.pending
        self.code: Optional[int] = None
        self.lines: list[str] = []
        self._subscribers: list[asyncio.Queue] = []
        self.done = asyncio.Event()

    def emit(self, line: str) -> None:
        self.lines.append(line)
        for q in self._subscribers:
            q.put_nowait(line)

    def subscribe(self) -> asyncio.Queue:
        """Return a queue pre-loaded with backlog; None is the end sentinel."""
        q: asyncio.Queue = asyncio.Queue()
        for line in self.lines:
            q.put_nowait(line)
        if self.done.is_set():
            q.put_nowait(None)
        else:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)


class JobStore:
    """In-memory store. Jobs are lost on restart — fine for the test stage."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def create(self, prompt: str) -> Job:
        job = Job(prompt)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)


store = JobStore()


async def run_job(job: Job) -> None:
    """Open an IAP tunnel, stream claude output line-by-line to all subscribers.

    The tunnel and SSH session are scoped to this job — they close when claude exits.
    The HTTP/WS connection can drop at any time; the job keeps running and buffering.
    """
    job.status = JobStatus.running
    cmd = f"{shlex.quote(settings.claude_bin)} -p {shlex.quote(job.prompt)} --dangerously-skip-permissions"
    try:
        async with iap_ssh() as conn:
            async with conn.create_process(cmd, stderr=asyncssh.STDOUT) as proc:
                async for raw in proc.stdout:
                    job.emit(raw.rstrip("\n"))
            job.code = proc.exit_status if proc.exit_status is not None else -1
            job.status = JobStatus.done if job.code == 0 else JobStatus.error
    except Exception as exc:
        job.emit(f"[runner error] {exc}")
        job.status = JobStatus.error
        job.code = -1
    finally:
        job.done.set()
        for q in list(job._subscribers):
            q.put_nowait(None)
