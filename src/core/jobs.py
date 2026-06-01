import json
import subprocess
import uuid
from enum import Enum
from typing import Optional

import redis as sync_redis

from src.core.celery_app import app as celery_app
from src.core.config import settings

STREAM_DONE_SENTINEL = "__done__"


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"


def _redis() -> sync_redis.Redis:
    return sync_redis.from_url(settings.redis_url, decode_responses=True)


def create_job(prompt: str) -> str:
    job_id = uuid.uuid4().hex
    _redis().hset(f"job:{job_id}", mapping={"status": JobStatus.pending, "prompt": prompt, "code": ""})
    return job_id


def get_job_state(job_id: str) -> Optional[dict]:
    r = _redis()
    data = r.hgetall(f"job:{job_id}")
    if not data:
        return None
    data["lines"] = r.lrange(f"job:{job_id}:output", 0, -1)
    return data


@celery_app.task(name="run_claude")
def run_claude_task(job_id: str, prompt: str) -> None:
    r = _redis()
    channel = f"job:{job_id}:stream"
    r.hset(f"job:{job_id}", "status", JobStatus.running)
    try:
        proc = subprocess.Popen(
            [settings.claude_bin, "-p", prompt, "--dangerously-skip-permissions"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            idx = r.rpush(f"job:{job_id}:output", line) - 1  # 0-based index
            r.publish(channel, json.dumps({"idx": idx, "data": line}))
        proc.wait()
        code = proc.returncode or 0
        status = JobStatus.done if code == 0 else JobStatus.error
    except Exception as exc:
        line = f"[runner error] {exc}"
        idx = r.rpush(f"job:{job_id}:output", line) - 1
        r.publish(channel, json.dumps({"idx": idx, "data": line}))
        code = -1
        status = JobStatus.error

    r.hset(f"job:{job_id}", mapping={"status": status, "code": code})
    r.publish(channel, json.dumps({STREAM_DONE_SENTINEL: True, "status": status, "code": code}))
