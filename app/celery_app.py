from celery import Celery
from app.config import settings

celery_app = Celery(
    "media_pipeline",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Retry policy: transient failures (e.g. a momentarily locked file,
    # a flaky OCR call) get retried with backoff; we don't want one bad
    # image to spin forever, so it's capped.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
