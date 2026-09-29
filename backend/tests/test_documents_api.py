import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError

from app.api import deps
from app.api import documents as documents_api
from app.api.deps import CurrentUser, get_current_user
from app.database import get_db
from app.main import app
from app.services.documents import DocumentNotFoundError

USER = CurrentUser(id=uuid.UUID("11111111-1111-1111-1111-111111111111"), email="a@example.com")
DOC_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def fake_document(**overrides):
    values = dict(
        id=DOC_ID, user_id=USER.id, title="Doc", filename="doc.pdf", status="processing",
        page_count=None, summary=None, questions=None, storage_path=f"{USER.id}/{DOC_ID}.pdf",
        created_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def authed_client():
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- authentication -------------------------------------------------------

def test_missing_token_returns_401() -> None:
    response = TestClient(app).get("/documents")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(_token):
        raise AuthApiError("invalid JWT", 401, "bad_jwt")

    fake = SimpleNamespace(auth=SimpleNamespace(get_user=reject))
    monkeypatch.setattr(deps, "get_supabase", lambda: fake)
    response = TestClient(app).get("/documents", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired session."}


def test_valid_token_resolves_user(monkeypatch: pytest.MonkeyPatch) -> None:
    user = SimpleNamespace(id=str(USER.id), email=USER.email)
    fake = SimpleNamespace(auth=SimpleNamespace(get_user=lambda _t: SimpleNamespace(user=user)))
    monkeypatch.setattr(deps, "get_supabase", lambda: fake)
    response = TestClient(app).get("/auth/me", headers={"Authorization": "Bearer good"})
    assert response.status_code == 200
    assert response.json() == {"id": str(USER.id), "email": USER.email}


# --- ownership & responses ------------------------------------------------

def test_user_id_comes_from_token_not_request(authed_client, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    def get_owned(db, user_id, document_id):
        seen.update(user_id=user_id, document_id=document_id)
        return fake_document()

    monkeypatch.setattr(documents_api.document_service, "get_owned_document", get_owned)
    response = authed_client.get(f"/documents/{DOC_ID}?user_id={uuid.uuid4()}")
    assert response.status_code == 200
    assert seen == {"user_id": USER.id, "document_id": DOC_ID}


def test_storage_path_is_never_exposed(authed_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents_api.document_service, "list_documents", lambda db, uid: [fake_document()])
    response = authed_client.get("/documents")
    assert response.status_code == 200
    assert "storage_path" not in response.json()[0]


def test_other_users_document_returns_404(authed_client, monkeypatch: pytest.MonkeyPatch) -> None:
    def not_found(*_args):
        raise DocumentNotFoundError()

    monkeypatch.setattr(documents_api.document_service, "get_owned_document", not_found)
    monkeypatch.setattr(documents_api.document_service, "delete_document", not_found)
    assert authed_client.get(f"/documents/{DOC_ID}").json() == {"detail": "Document not found."}
    assert authed_client.delete(f"/documents/{DOC_ID}").status_code == 404


def test_malformed_document_id_returns_422(authed_client) -> None:
    assert authed_client.get("/documents/not-a-uuid").status_code == 422


def test_upload_rejects_non_pdf_before_storing(authed_client, monkeypatch: pytest.MonkeyPatch) -> None:
    called = []
    monkeypatch.setattr(documents_api, "ingest_pdf", lambda *a, **k: called.append(1))
    response = authed_client.post(
        "/documents/upload", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 415
    assert called == []


def test_unexpected_errors_hide_internals(authed_client, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args):
        raise RuntimeError("connection string postgres://secret")

    monkeypatch.setattr(documents_api.document_service, "list_documents", boom)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/documents")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
