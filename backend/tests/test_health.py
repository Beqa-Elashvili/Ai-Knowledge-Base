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
