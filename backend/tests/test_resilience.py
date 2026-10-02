"""Dropped connections to Supabase and unexpected errors must not surface as
opaque browser network failures."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api import documents as documents_api
from app.main import app
from app.services import storage

USER_ID = "11111111-1111-1111-1111-111111111111"
ORIGIN = {"Origin": "http://localhost:3000"}


def flaky(failures: int, result=None):
    """A callable that raises 'Server disconnected' `failures` times, then returns `result`."""
    calls = []

    def call(*_args, **_kwargs):
        calls.append(1)
        if len(calls) <= failures:
            raise httpx.RemoteProtocolError("Server disconnected")
        return result

    call.calls = calls
    return call


def fake_supabase(get_user):
    return SimpleNamespace(auth=SimpleNamespace(get_user=get_user))


def test_stale_connection_is_retried_once(monkeypatch: pytest.MonkeyPatch) -> None:
    user = SimpleNamespace(user=SimpleNamespace(id=USER_ID, email="a@example.com"))
    get_user = flaky(failures=1, result=user)
    monkeypatch.setattr(deps, "get_supabase", lambda: fake_supabase(get_user))

    response = TestClient(app).get("/auth/me", headers={"Authorization": "Bearer t"})

    assert response.status_code == 200 and response.json()["id"] == USER_ID
    assert len(get_user.calls) == 2


def test_auth_service_down_is_a_clear_502_with_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    get_user = flaky(failures=5)
    monkeypatch.setattr(deps, "get_supabase", lambda: fake_supabase(get_user))

    response = TestClient(app).get("/documents", headers={"Authorization": "Bearer t", **ORIGIN})

    assert response.status_code == 502
    assert response.json() == {"detail": "Could not verify your session right now. Please try again."}
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert len(get_user.calls) == 2  # one retry, no more


def test_unexpected_500_keeps_cors_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without CORS headers the browser hides the 500 as a network error."""
    from app.api.deps import CurrentUser, get_current_user
    from app.database import get_db

    def boom(*_args):
        raise RuntimeError("secret connection string")

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=USER_ID, email=None)
    app.dependency_overrides[get_db] = lambda: None
    monkeypatch.setattr(documents_api.document_service, "list_documents", boom)
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/documents", headers=ORIGIN)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_storage_retries_then_reports_storage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    remove = flaky(failures=1)
    monkeypatch.setattr(storage, "_bucket", lambda: SimpleNamespace(remove=remove))
    storage.delete_file("u/d.pdf")
    assert len(remove.calls) == 2

    always = flaky(failures=5)
    monkeypatch.setattr(storage, "_bucket", lambda: SimpleNamespace(remove=always))
    with pytest.raises(storage.StorageError):
        storage.delete_file("u/d.pdf")
