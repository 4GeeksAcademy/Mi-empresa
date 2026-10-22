FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/api

WORKDIR /app/api

COPY services/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir uv \
    && uv pip install --system -r requirements.txt

COPY services/api ./
COPY packages /app/packages
COPY services/telemetry /app/services/telemetry
COPY services/reporting /app/services/reporting
COPY services/job_runner.py /app/services/job_runner.py
COPY services/celery_app.py services/incident_tasks.py services/task_store.py /app/services/
COPY scripts /app/scripts
COPY data/pipelines /app/data/pipelines
COPY data/process /app/data/process
COPY docs/telemetry /docs/telemetry

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]