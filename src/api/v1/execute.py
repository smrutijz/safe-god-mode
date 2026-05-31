import asyncio

from fastapi import APIRouter, HTTPException

from src.core.config import settings
from src.models.schemas import ExecResult, Query

router = APIRouter(tags=["sync"])


@router.post("/execute", response_model=ExecResult)
async def execute(q: Query):
    """SYNC: blocks until claude exits, then returns the whole output.

    Only safe for short runs — the connection is held the entire time, so a run
    longer than the 15-min gate will be orphaned. Use /jobs for long work.
    """
    proc = await asyncio.create_subprocess_exec(
        settings.claude_bin, "-p", q.prompt, "--dangerously-skip-permissions",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(), timeout=q.timeout or settings.sync_timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise HTTPException(status_code=504, detail="claude run exceeded timeout")

    return ExecResult(
        code=proc.returncode or 0,
        stdout=out.decode(errors="replace"),
        stderr=err.decode(errors="replace"),
    )
