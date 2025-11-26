#
# FILE: app/workers/celery_app.py
from celery import Celery
from app.config import settings

celery_app = Celery(
    "drone_architect_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_track_started=True
)

# Auto-discover tasks in the 'workers' package
celery_app.conf.imports = ['app.workers.tasks']