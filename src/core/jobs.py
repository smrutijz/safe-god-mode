import asyncio
import uuid
from enum import Enum
from typing import Optional
from src.core.config import settings


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
        self.lines: list[str] = []                  # full output, for late pollers
        self._subscribers: list[asyncio.Queue] = []  # live websocket listeners
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
    """Run claude to completion, regardless of who is (or isn't) listening.

    This is what survives the 15-min gate: the HTTP/WS connection can drop, the
    job keeps running and buffering output here.
    """
    job.status = JobStatus.running
    try:
        proc = await asyncio.create_subprocess_exec(
            settings.claude_bin, "-p", job.prompt, "--dangerously-skip-permissions",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # merge so streaming is single-channel
        )
        assert proc.stdout is not None
        async for raw in proc.stdout:
            job.emit(raw.decode(errors="replace").rstrip("\n"))
        await proc.wait()
        job.code = proc.returncode
        job.status = JobStatus.done if proc.returncode == 0 else JobStatus.error
    except Exception as exc:  # noqa: BLE001 - surface any spawn/runtime failure
        job.emit(f"[runner error] {exc}")
        job.status = JobStatus.error
        job.code = -1
    finally:
        job.done.set()
        for q in list(job._subscribers):
            q.put_nowait(None)  # tell live listeners the stream ended
