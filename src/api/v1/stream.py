from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.jobs import store

router = APIRouter(tags=["stream"])


@router.websocket("/ws/jobs/{job_id}")
async def stream(ws: WebSocket, job_id: str):
    """STREAM: live output for a job, line by line, as it is produced.

    Replays any backlog first, then follows. If the socket drops at the 15-min
    gate, just reconnect — the backlog replay catches you up. The job keeps
    running either way.
    """
    await ws.accept()
    job = store.get(job_id)
    if job is None:
        await ws.send_json({"event": "error", "detail": "unknown job"})
        await ws.close()
        return

    q = job.subscribe()
    try:
        while True:
            line = await q.get()
            if line is None:  # end sentinel
                await ws.send_json(
                    {"event": "end", "status": job.status, "code": job.code}
                )
                break
            await ws.send_json({"event": "line", "data": line})
    except WebSocketDisconnect:
        pass
    finally:
        job.unsubscribe(q)
