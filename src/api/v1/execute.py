import asyncio
import shlex

from fastapi import APIRouter, HTTPException

from src.core.config import settings
from src.core.iap import iap_ssh
from src.models.schemas import ExecResult, Query

router = APIRouter(tags=["sync"])


@router.post("/execute", response_model=ExecResult)
async def execute(q: Query):
    """SYNC: opens an IAP tunnel, runs claude on the VM, returns the full output.

    Only safe for short runs — the HTTP connection is held the entire time.
    Use /jobs for anything that might exceed the 15-min gateway timeout.
    """
    cmd = f"{shlex.quote(settings.claude_bin)} -p {shlex.quote(q.prompt)} --dangerously-skip-permissions"
    try:
        async with iap_ssh() as conn:
            result = await asyncio.wait_for(
                conn.run(cmd, check=False),
                timeout=q.timeout or settings.sync_timeout,
            )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="claude run exceeded timeout")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return ExecResult(
        code=result.exit_status if result.exit_status is not None else -1,
        stdout=result.stdout,
        stderr=result.stderr,
    )
