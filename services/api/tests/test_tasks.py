from __future__ import annotations

import io
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from services import task_store
from services.celery_app import app as celery_app
from services.incident_tasks import analyze_incidents_task


@pytest.fixture
def task_data(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_DATA_DIR", str(tmp_path))
    return tmp_path


def upload(contents: bytes) -> str:
    task_id = str(uuid4())
    task_store.create_upload(task_id, "21", "incidents.csv", io.BytesIO(contents))
    return task_id


def test_celery_configuration():
    assert celery_app.conf.broker_url == celery_app.conf.result_backend
    assert celery_app.conf.task_acks_late
    assert celery_app.conf.task_reject_on_worker_lost
    assert celery_app.conf.task_track_started
    assert celery_app.conf.worker_send_task_events
    assert celery_app.conf.task_soft_time_limit < celery_app.conf.task_time_limit
    assert celery_app.conf.task_time_limit < celery_app.conf.visibility_timeout
    assert analyze_incidents_task.max_retries == 3


def test_success_preserves_export_and_is_idempotent(task_data):
    task_id = upload(b"incident_id,category,status,satisfaction_score\nI-1,tracking,cerrado,5\n")
    result = analyze_incidents_task.apply(args=[task_id], task_id=task_id)
    assert result.successful(), str(result.result)
    assert result.result["summary"]["total_processed"] == 1
    assert b"total_processed,1" in task_store.latest_export()
    task_store.task_path(task_id, "csv").unlink()
    repeated = analyze_incidents_task.apply(args=[task_id], task_id=task_id)
    assert repeated.result == result.result
    assert task_store.get_failure(task_id) is None


def test_three_failures_retry_with_backoff_then_persist_dlq(task_data, monkeypatch):
    task_id = upload(b"wrong,header\nbad,data\n")
    countdowns = []
    original_retry = analyze_incidents_task.retry

    def retry(*, exc, countdown):
        countdowns.append(countdown)
        return original_retry(exc=exc, countdown=countdown)

    monkeypatch.setattr(analyze_incidents_task, "retry", retry)
    result = analyze_incidents_task.apply(args=[task_id], task_id=task_id)
    assert result.failed()
    assert countdowns == [2, 4]
    failure = task_store.get_failure(task_id)
    assert failure["task_id"] == task_id
    assert failure["attempt"] == 3
    assert failure["timestamp"]
    assert failure["error"]


def test_empty_upload_is_not_registered(task_data):
    with pytest.raises(ValueError):
        upload(b"")
    assert list(task_data.iterdir()) == []


@pytest.fixture
def task_client(task_data):
    from fastapi.testclient import TestClient
    from auth import get_current_user
    from main import app

    app.dependency_overrides[get_current_user] = lambda: {"id": 21}
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def test_post_only_enqueues_identifier_under_200ms(task_client, monkeypatch):
    published = []
    monkeypatch.setattr(analyze_incidents_task, "apply_async", lambda **kwargs: published.append(kwargs))
    started = time.perf_counter()
    response = task_client.post(
        "/api/incidents/analyze", files={"file": ("incidents.csv", b"large,csv\n1,2\n")},
    )
    elapsed = time.perf_counter() - started
    assert response.status_code == 202
    assert elapsed < 0.2
    task_id = response.json()["task_id"]
    assert response.json() == {"task_id": task_id}
    assert published == [{"args": [task_id], "task_id": task_id}]
    assert task_store.task_path(task_id, "csv").read_bytes() == b"large,csv\n1,2\n"


@pytest.mark.parametrize("state, expected", [
    ("PENDING", "pending"), ("RECEIVED", "pending"), ("RETRY", "pending"),
    ("STARTED", "started"), ("SUCCESS", "success"), ("FAILURE", "failure"),
])
def test_status_maps_celery_states(task_client, monkeypatch, state, expected):
    task_id = upload(b"some,csv\n")
    payload = {"summary": {"total_processed": 1}} if state == "SUCCESS" else None
    monkeypatch.setattr(celery_app, "AsyncResult", lambda identifier: SimpleNamespace(state=state, result=payload))
    response = task_client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json() == {"task_id": task_id, "status": expected, "result": payload}


def test_status_unknown_foreign_and_unauthenticated(task_client):
    from main import app

    task_id = upload(b"some,csv\n")
    assert task_client.get(f"/tasks/{uuid4()}").status_code == 404
    with task_store.connection() as database:
        database.execute("UPDATE tasks SET owner = 'other' WHERE task_id = ?", (task_id,))
    assert task_client.get(f"/tasks/{task_id}").status_code == 404
    app.dependency_overrides.clear()
    assert task_client.get(f"/tasks/{task_id}").status_code == 401


def test_export_and_terminal_status_survive_backend_expiration(task_client):
    task_id = upload(b"incident_id,category,status,satisfaction_score\nI-1,tracking,cerrado,5\n")
    result = analyze_incidents_task.apply(args=[task_id], task_id=task_id)
    assert task_client.get(f"/tasks/{task_id}").json()["result"] == result.result
    export = task_client.get("/api/incidents/results/export")
    assert export.status_code == 200
    assert b"total_processed,1" in export.content
    failed_id = upload(b"bad,csv\n")
    task_store.record_failure(failed_id, 3, "private failure")
    failure = task_client.get(f"/tasks/{failed_id}")
    assert failure.json() == {"task_id": failed_id, "status": "failure", "result": None}


def test_broker_failure_returns_503_and_retains_input(task_client, monkeypatch):
    from kombu.exceptions import OperationalError

    def unavailable(**kwargs):
        raise OperationalError("broker unavailable")

    monkeypatch.setattr(analyze_incidents_task, "apply_async", unavailable)
    response = task_client.post("/api/incidents/analyze", files={"file": ("test.csv", b"some,csv\n")})
    assert response.status_code == 503
    task_id = response.json()["detail"]["task_id"]
    assert task_store.get_job(task_id)
    assert task_store.task_path(task_id, "csv").exists()


def test_docker_queue_lifecycle(tmp_path):
    import base64
    import json
    import os
    import socket
    import subprocess
    from threading import Event

    import httpx
    import redis

    if os.environ.get("DEV55_DOCKER_TEST") != "1":
        pytest.skip("Set DEV55_DOCKER_TEST=1 after building trackflow-dev55-check")

    image = os.environ.get("DEV55_TEST_IMAGE", "trackflow-dev55-check")
    host_network = os.environ.get("DEV55_HOST_NETWORK") == "1"
    prefix = f"dev55-{uuid4().hex[:8]}"
    network = f"{prefix}-network"
    volume = f"{prefix}-data"
    containers = []

    def free_port():
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    api_port = free_port() if host_network else 8000
    flower_port = free_port() if host_network else 5555
    redis_port = free_port()

    def docker(*arguments):
        return subprocess.run(
            ["docker", *arguments], check=True, text=True, capture_output=True,
        ).stdout.strip()

    def eventually(check, timeout=90):
        deadline = time.monotonic() + timeout
        while True:
            try:
                return check()
            except (AssertionError, httpx.TransportError, redis.RedisError):
                if time.monotonic() >= deadline:
                    raise
                Event().wait(0.1)

    def run(name, container_image, *command, publish=None, environment=(), storage=False):
        container = f"{prefix}-{name}"
        use_host = host_network and name != "redis"
        arguments = ["run", "-d", "--name", container, "--network", "host" if use_host else network]
        if publish and not use_host:
            arguments.extend(["-p", f"127.0.0.1:{publish}"])
        if storage:
            arguments.extend(["-v", f"{volume}:/evaluation"])
        for variable in environment:
            arguments.extend(["-e", variable])
        docker(*arguments, container_image, *command)
        containers.append(container)
        return container

    def port(container, number):
        if container == f"{prefix}-redis":
            return redis_port
        if host_network and container != f"{prefix}-redis":
            return number
        return int(docker("port", container, f"{number}/tcp").rsplit(":", 1)[1])

    docker("network", "create", network)
    docker("volume", "create", volume)
    try:
        broker = run(
            "redis", "redis:7.4-alpine", "redis-server", "--appendonly", "yes",
            "--appendfsync", "always", "--maxmemory-policy", "noeviction",
            publish=f"{redis_port}:6379",
        )
        redis_client = redis.Redis(host="127.0.0.1", port=port(broker, 6379))
        eventually(lambda: redis_client.ping())
        assert redis_client.config_get("maxmemory-policy")["maxmemory-policy"] == "noeviction"
        assert redis_client.config_get("appendonly")["appendonly"] == "yes"
        broker_address = f"127.0.0.1:{port(broker, 6379)}" if host_network else f"{broker}:6379"
        environment = (
            f"REDIS_URL=redis://{broker_address}/0", "TASK_DATA_DIR=/evaluation/tasks",
            "DATABASE_URL=sqlite:////evaluation/inventory.db",
            "TRACKFLOW_AUTH_DB_PATH=/evaluation/auth.json",
            "SECRET_KEY=dev55-isolated-integration-key-not-production",
        )
        api = run(
            "api", image, "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(api_port),
            publish=f"{api_port}:{api_port}", environment=environment, storage=True,
        )
        flower = run(
            "flower", image, "celery", "-A", "services.celery_app", "flower", f"--port={flower_port}",
            "--persistent=True", "--db=/evaluation/flower",
            publish=f"{flower_port}:{flower_port}",
            environment=environment + ("FLOWER_UNAUTHENTICATED_API=true",), storage=True,
        )
        client = httpx.Client(base_url=f"http://127.0.0.1:{port(api, api_port)}", timeout=30)
        flower_client = httpx.Client(base_url=f"http://127.0.0.1:{port(flower, flower_port)}", timeout=10)

        def ready():
            assert client.get("/health").status_code == 200
            assert flower_client.get("/").status_code == 200

        eventually(ready)
        registered = client.post("/users", json={
            "email": "queue-evaluation@example.test", "password": "Dev55-test-password",
        })
        assert registered.status_code == 201, registered.text
        login = client.post("/auth/login", json={
            "email": "queue-evaluation@example.test", "password": "Dev55-test-password",
        })
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        def status(task_id, expected):
            response = client.get(f"/tasks/{task_id}")
            assert response.status_code == 200, response.text
            assert response.json()["status"] == expected, response.text
            return response.json()

        csv_bytes = b"incident_id,category,status,satisfaction_score\n" + b"I-1,tracking,cerrado,5\n" * 200_000
        before = time.perf_counter()
        accepted = client.post("/api/incidents/analyze", files={"file": ("large.csv", csv_bytes)})
        latency = time.perf_counter() - before
        assert accepted.status_code == 202, accepted.text
        assert latency < 0.2, f"Acceptance latency: {latency * 1000:.1f}ms"
        success_id = accepted.json()["task_id"]
        status(success_id, "pending")
        message = json.loads(redis_client.lindex("celery", 0))
        body = json.loads(base64.b64decode(message["body"]))
        assert body[0] == [success_id]
        assert len(message["body"]) < 512
        docker("restart", broker)
        eventually(lambda: redis_client.ping())
        assert redis_client.llen("celery") == 1
        worker = run(
            "worker", image, "celery", "-A", "services.celery_app", "worker", "--loglevel=INFO",
            "--concurrency=1", "--events", environment=environment, storage=True,
        )
        eventually(lambda: status(success_id, "started"))
        running_at = time.perf_counter()
        docker("stop", "--time", "10", api)
        assert docker("inspect", "-f", "{{.State.Running}}", worker) == "true"

        def completed_without_api():
            stored = redis_client.get(f"celery-task-meta-{success_id}")
            assert stored is not None
            result = json.loads(stored)
            assert result["status"] == "SUCCESS", result
            return result

        completed = eventually(completed_without_api)
        task_duration = time.perf_counter() - running_at
        assert completed["result"]["summary"]["total_processed"] == 200_000
        docker("start", api)
        eventually(lambda: status(success_id, "success"))
        export = client.get("/api/incidents/results/export")
        assert export.status_code == 200
        assert b"total_processed,200000" in export.content

        failed = client.post("/api/incidents/analyze", files={"file": ("invalid.csv", b"wrong,header\n1,2\n")})
        assert failed.status_code == 202
        failure_id = failed.json()["task_id"]
        eventually(lambda: status(failure_id, "failure"))
        dlq = json.loads(docker("exec", worker, "python", "-c",
            "import json; from services.task_store import get_failure; "
            f"print(json.dumps(get_failure('{failure_id}')))"))
        assert dlq["attempt"] == 3 and dlq["error"] and dlq["timestamp"]

        def flower_has_terminal_tasks():
            response = flower_client.get("/api/tasks")
            assert response.status_code == 200, response.text
            tasks = response.json()
            assert tasks.get(success_id, {}).get("state") == "SUCCESS", tasks
            assert tasks.get(failure_id, {}).get("state") == "FAILURE", tasks
            return tasks

        observed = eventually(flower_has_terminal_tasks)
        assert observed[failure_id]["retries"] == 2
        combined_logs = subprocess.run(["docker", "logs", worker], capture_output=True, text=True, check=True)
        logs = combined_logs.stdout + combined_logs.stderr
        for identifier in (success_id, failure_id):
            assert identifier in logs
        assert "countdown=2" in logs and "countdown=4" in logs
        assert "attempt=3 state=failure" in logs
        assert "duration=" in logs
        evidence = {
            "network_mode": "host" if host_network else "bridge",
            "latency_ms": round(latency * 1000, 2), "task_seconds_after_started": round(task_duration, 2),
            "success_id": success_id, "failure_id": failure_id, "dlq": dlq,
            "flower_states": {success_id: observed[success_id]["state"], failure_id: observed[failure_id]["state"]},
            "redis_restart_preserved_queue": True, "worker_completed_without_api": True,
        }
        print("DEV55_EVIDENCE " + json.dumps(evidence))
        client.close()
        flower_client.close()
    except Exception:
        for container in containers:
            output = subprocess.run(["docker", "logs", "--tail", "35", container], capture_output=True, text=True)
            print(f"{container}:\n{output.stdout}\n{output.stderr}")
        raise
    finally:
        for container in reversed(containers):
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", volume], capture_output=True, check=False)
        subprocess.run(["docker", "network", "rm", network], capture_output=True, check=False)