import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app.errors import ExternalServiceError
from app.services import documents as service
from app.services.uploads import ValidatedPdf

USER = uuid.UUID("11111111-1111-1111-1111-111111111111")
PDF = ValidatedPdf(filename="book.pdf", data=b"%PDF-1.7")


class FailingSession:
    def __init__(self) -> None:
        self.rolled_back = False

    def add(self, _obj) -> None:
        pass

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        raise OperationalError("insert", {}, Exception("db down"))

    def rollback(self) -> None:
        self.rolled_back = True


def test_failed_insert_removes_uploaded_file(monkeypatch: pytest.MonkeyPatch) -> None:
    uploaded, deleted = [], []
    monkeypatch.setattr(service.storage, "upload_pdf", lambda u, d, data: uploaded.append(f"{u}/{d}.pdf") or uploaded[-1])
    monkeypatch.setattr(service.storage, "delete_file", deleted.append)

    db = FailingSession()
    with pytest.raises(ExternalServiceError):
        service.create_document(db, USER, PDF, page_count=1, chunks=[])

    assert db.rolled_back
    assert deleted == uploaded and len(uploaded) == 1


def test_failed_upload_creates_no_record(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_upload(*_args):
        raise service.storage.StorageError()

    monkeypatch.setattr(service.storage, "upload_pdf", fail_upload)

    class NoWriteSession:
        def add(self, _obj):
            raise AssertionError("record must not be created when storage fails")

    with pytest.raises(service.storage.StorageError):
        service.create_document(NoWriteSession(), USER, PDF, page_count=1, chunks=[])
