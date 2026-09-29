import uuid
from typing import Any

import pytest
from storage3.exceptions import StorageApiError

from app.services import storage
from app.services.storage import StorageError, build_storage_path


class FakeBucket:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, Any]] = []

    def _maybe_fail(self) -> None:
        if self.fail:
            raise StorageApiError("secret internal detail", "InternalError", 500)

    def upload(self, path: str, data: bytes, file_options: dict[str, str]) -> None:
        self.calls.append(("upload", (path, data, file_options)))
        self._maybe_fail()

    def remove(self, paths: list[str]) -> list[dict[str, Any]]:
        self.calls.append(("remove", paths))
        self._maybe_fail()
        return []

    def create_signed_url(self, path: str, expires_in: int) -> dict[str, str]:
        self.calls.append(("sign", (path, expires_in)))
        self._maybe_fail()
        return {"signedUrl": f"https://example.test/{path}?token=t"}


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch) -> FakeBucket:
    fake = FakeBucket()
    monkeypatch.setattr(storage, "_bucket", lambda: fake)
    return fake


USER = uuid.UUID("11111111-1111-1111-1111-111111111111")
DOC = uuid.UUID("22222222-2222-2222-2222-222222222222")


def test_storage_path_is_user_folder_and_document_id() -> None:
    assert build_storage_path(USER, DOC) == f"{USER}/{DOC}.pdf"


def test_upload_sets_pdf_content_type_and_never_upserts(bucket: FakeBucket) -> None:
    path = storage.upload_pdf(USER, DOC, b"%PDF-1.7")
    assert path == f"{USER}/{DOC}.pdf"
    _, (called_path, data, options) = bucket.calls[0]
    assert called_path == path and data == b"%PDF-1.7"
    assert options == {"content-type": "application/pdf", "upsert": "false"}


def test_signed_url(bucket: FakeBucket) -> None:
    assert storage.create_signed_url("a/b.pdf", expires_in=60).startswith("https://example.test/a/b.pdf")
    assert bucket.calls[0] == ("sign", ("a/b.pdf", 60))


def test_delete(bucket: FakeBucket) -> None:
    storage.delete_file("a/b.pdf")
    assert bucket.calls[0] == ("remove", ["a/b.pdf"])


@pytest.mark.parametrize(
    "call",
    [
        lambda: storage.upload_pdf(USER, DOC, b"x"),
        lambda: storage.delete_file("a/b.pdf"),
        lambda: storage.create_signed_url("a/b.pdf"),
    ],
)
def test_errors_are_wrapped_without_leaking_details(bucket: FakeBucket, call) -> None:
    bucket.fail = True
    with pytest.raises(StorageError) as info:
        call()
    assert "secret internal detail" not in str(info.value)


def test_readiness_requires_documents_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app import supabase_client

    fake_client = SimpleNamespace(storage=SimpleNamespace(list_buckets=lambda: [SimpleNamespace(name="other")]))
    monkeypatch.setattr(supabase_client, "get_supabase", lambda: fake_client)
    with pytest.raises(RuntimeError):
        supabase_client.check_supabase()
