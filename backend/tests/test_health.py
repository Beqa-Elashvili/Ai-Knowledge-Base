from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "AI Knowledge Base API is running"}


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_available() -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_hidden_in_production(monkeypatch) -> None:
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        production = TestClient(create_app())
        assert production.get("/docs").status_code == 404
        assert production.get("/openapi.json").status_code == 404
        assert production.get("/health").status_code == 200
    finally:
        monkeypatch.delenv("ENVIRONMENT")
        get_settings.cache_clear()


def test_readiness_ok(monkeypatch) -> None:
    monkeypatch.setattr("app.api.health.check_database", lambda: {"pgvector_available": True})
    monkeypatch.setattr("app.api.health.check_supabase", lambda: {"buckets": []})
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_failure_hides_error_details(monkeypatch) -> None:
    def boom() -> None:
        raise RuntimeError("password authentication failed for user postgres: s3cret")

    monkeypatch.setattr("app.api.health.check_database", boom)
    monkeypatch.setattr("app.api.health.check_supabase", lambda: {"buckets": []})
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["database"]["status"] == "error"
    assert "s3cret" not in response.text
