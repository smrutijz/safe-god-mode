from celery import Celery

from src.core.config import settings

app = Celery(
    "safe-god-mode",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.core.jobs"],
)
app.conf.task_track_started = True
