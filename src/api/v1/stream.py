import json

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.config import settings
from src.core.jobs import STREAM_DONE_SENTINEL

router = APIRouter(tags=["stream"])


@router.websocket("/ws/jobs/{job_id}")
async def stream(ws: WebSocket, job_id: str):
    """STREAM: live output for a job, line by line, as it is produced.

    Subscribes to Redis pub/sub BEFORE replaying the backlog so no lines are
    missed. Any pub/sub message with idx < backlog length is skipped (already
    sent). Reconnecting after a drop replays the full backlog automatically.
    """
    await ws.accept()

    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = r.pubsub()
    channel = f"job:{job_id}:stream"

    try:
        # Subscribe first to avoid a race between backlog fetch and new lines.
        await pubsub.subscribe(channel)

        state = await r.hgetall(f"job:{job_id}")
        if not state:
            await ws.send_json({"event": "error", "detail": "unknown job"})
            return

        backlog = await r.lrange(f"job:{job_id}:output", 0, -1)
        for line in backlog:
            await ws.send_json({"event": "line", "data": line})
        sent_count = len(backlog)

        if state.get("status") in ("done", "error"):
            code_str = state.get("code", "")
            await ws.send_json({
                "event": "end",
                "status": state["status"],
                "code": int(code_str) if code_str else None,
            })
            return

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            payload = json.loads(message["data"])
            if STREAM_DONE_SENTINEL in payload:
                await ws.send_json({
                    "event": "end",
                    "status": payload["status"],
                    "code": payload["code"],
                })
                break
            # Skip lines already covered by the backlog replay.
            if payload["idx"] >= sent_count:
                await ws.send_json({"event": "line", "data": payload["data"]})
                sent_count += 1

    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await r.aclose()
