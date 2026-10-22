from __future__ import annotations

import os

from celery import Celery


redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
app = Celery(
    "trackflow",
    broker=redis_url,
    backend=redis_url,
    include=["services.incident_tasks"],
)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_soft_time_limit=270,
    task_time_limit=300,
    broker_transport_options={"visibility_timeout": 3600, "socket_timeout": 1},
    result_backend_transport_options={"visibility_timeout": 3600},
    visibility_timeout=3600,
    broker_connection_timeout=1,
    broker_connection_retry_on_startup=True,
    task_publish_retry=False,
    redis_socket_connect_timeout=1,
    redis_socket_timeout=1,
    result_expires=86400,
)