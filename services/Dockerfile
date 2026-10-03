FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/api

COPY services/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir uv \
    && uv pip install --system -r requirements.txt

COPY services/api ./
COPY docs/telemetry /docs/telemetry

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]