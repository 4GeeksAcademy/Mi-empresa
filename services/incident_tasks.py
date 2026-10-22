from __future__ import annotations

import csv
import io
import json
import logging
import time

from celery import Task

from incidents.analysis import analyze_incidents_csv
from services.celery_app import app
from services import task_store


logger = logging.getLogger(__name__)


class IncidentTask(Task):
    max_retries = 3

    def before_start(self, task_id, args, kwargs):
        self.request.started_at = time.monotonic()
        self.log_state(task_id, "started")

    def log_state(self, task_id, state, error=None):
        duration = time.monotonic() - getattr(self.request, "started_at", time.monotonic())
        logger.info(
            "task_id=%s attempt=%s state=%s duration=%.6fs error=%s",
            task_id, self.request.retries + 1, state, duration, error,
        )

    def on_success(self, retval, task_id, args, kwargs):
        self.log_state(task_id, "success")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        self.log_state(task_id, "pending", str(exc))

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        task_store.record_failure(task_id, self.request.retries + 1, str(exc))
        self.log_state(task_id, "failure", str(exc))


@app.task(bind=True, base=IncidentTask, name="trackflow.analyze_incidents")
def analyze_incidents_task(self, task_id: str) -> dict:
    try:
        job = task_store.get_job(task_id)
        if job is None:
            raise ValueError("No existe la referencia del CSV.")
        if job["result"] is not None:
            return json.loads(job["result"])
        csv_text = task_store.task_path(task_id, "csv").read_text(encoding="utf-8-sig")
        analysis = analyze_incidents_csv(csv_text)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["metric", "value"])
        writer.writerows(analysis.to_metrics_rows())
        result = {"filename": job["filename"], "summary": analysis.to_json()}
        task_store.complete_job(task_id, result, buffer.getvalue().encode("utf-8"))
        return result
    except Exception as exc:
        if self.request.retries >= 2:
            raise
        countdown = 2 ** (self.request.retries + 1)
        logger.warning(
            "task_id=%s attempt=%s countdown=%s error=%s",
            self.request.id, self.request.retries + 1, countdown, str(exc),
        )
        raise self.retry(exc=exc, countdown=countdown)