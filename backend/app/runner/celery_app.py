from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "cloudlab",
    broker=settings.redis_url,
    include=["app.runner.tasks"],
)
celery_app.conf.broker_connection_retry_on_startup = True
