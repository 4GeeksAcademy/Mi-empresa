from fastapi.testclient import TestClient
from fastapi import FastAPI

import main


def test_real_app_cors_preflight_allows_configured_origin_and_bearer_header(monkeypatch):
    monkeypatch.setenv("TRACKFLOW_CORS_ALLOWED_ORIGINS", "https://ops.example.test")
    app = FastAPI()
    main._configure_cors(app)
    app.get("/resource")(lambda: {"ok": True})

    response = TestClient(app).options(
        "/resource",
        headers={
            "Origin": "https://ops.example.test",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://ops.example.test"
    assert "access-control-allow-credentials" not in response.headers


def test_real_app_cors_does_not_grant_unlisted_origin(monkeypatch):
    monkeypatch.setenv("TRACKFLOW_CORS_ALLOWED_ORIGINS", "https://ops.example.test")
    app = FastAPI()
    main._configure_cors(app)
    app.get("/resource")(lambda: {"ok": True})
    response = TestClient(app).get("/resource", headers={"Origin": "https://evil.example"})

    assert response.status_code != 500
    assert "access-control-allow-origin" not in response.headers


def test_cors_configuration_rejects_wildcards_and_paths(monkeypatch):
    monkeypatch.setenv("TRACKFLOW_CORS_ALLOWED_ORIGINS", "*")
    try:
        main._cors_allowed_origins()
    except ValueError as error:
        assert "exact http(s) origins" in str(error)
    else:
        raise AssertionError("Wildcard CORS origins must be rejected")

    monkeypatch.setenv("TRACKFLOW_CORS_ALLOWED_ORIGINS", "https://ops.example.test/path")
    try:
        main._cors_allowed_origins()
    except ValueError as error:
        assert "exact http(s) origins" in str(error)
    else:
        raise AssertionError("CORS paths must be rejected")

    for invalid_origin in (
        "https://user:password@ops.example.test",
        "https://ops.example.test:99999",
    ):
        monkeypatch.setenv("TRACKFLOW_CORS_ALLOWED_ORIGINS", invalid_origin)
        try:
            main._cors_allowed_origins()
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid CORS origin must be rejected: {invalid_origin}")