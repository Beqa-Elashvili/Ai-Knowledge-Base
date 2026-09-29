"""Document endpoints. Thin HTTP layer: validation and persistence live in services."""

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.config import get_settings
from app.database import get_db
from app.schemas import DocumentResponse, ErrorResponse
from app.services import documents as document_service
from app.services.uploads import validate_pdf_upload

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    responses={401: {"model": ErrorResponse, "description": "Missing or invalid access token"}},
)

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Document not found"}}


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Empty or malformed file"},
        413: {"model": ErrorResponse, "description": "File exceeds the size limit"},
        415: {"model": ErrorResponse, "description": "Not a PDF"},
        502: {"model": ErrorResponse, "description": "Storage or database failure"},
    },
)
def upload_document(
    file: UploadFile = File(..., description="PDF file"),
    title: str | None = Form(None, max_length=200, description="Optional title; defaults to the file name"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    pdf = validate_pdf_upload(
        filename=file.filename,
        content_type=file.content_type,
        stream=file.file,
        max_bytes=get_settings().max_upload_size_bytes,
    )
    document = document_service.create_document(db, user.id, pdf, title=title)
    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentResponse]:
    return [DocumentResponse.model_validate(d) for d in document_service.list_documents(db, user.id)]


@router.get("/{document_id}", response_model=DocumentResponse, responses=NOT_FOUND)
def get_document(
    document_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    return DocumentResponse.model_validate(document_service.get_owned_document(db, user.id, document_id))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
def delete_document(
    document_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    document_service.delete_document(db, user.id, document_id)
