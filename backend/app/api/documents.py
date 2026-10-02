"""Document endpoints. Thin HTTP layer: validation and persistence live in services."""

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.config import get_settings
from app.database import get_db
from app.schemas import (
    AskRequest,
    AskResponse,
    DocumentResponse,
    ErrorResponse,
    GenerateRequest,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.services import documents as document_service
from app.services.ingestion import ingest_pdf
from app.services.questions import generate_questions
from app.services.rag import answer_question
from app.services.summaries import summarize_document
from app.services.uploads import validate_pdf_upload
from app.services.vector_search import search_document

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
        422: {"model": ErrorResponse, "description": "Damaged, password-protected or text-less PDF"},
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
    document = ingest_pdf(db, user.id, pdf, title=title)
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


@router.post(
    "/{document_id}/search",
    response_model=SearchResponse,
    responses={
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Document has no embeddings yet"},
        502: {"model": ErrorResponse, "description": "Embedding or database failure"},
    },
)
def search(
    document_id: uuid.UUID,
    body: SearchRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """Semantic search inside one of your documents: the chunks most similar
    to the question, best first. Retrieval only; no LLM answer."""
    chunks = search_document(db, user.id, document_id, body.question, top_k=body.top_k)
    return SearchResponse(
        document_id=document_id,
        question=body.question,
        results=[SearchResult.model_validate(chunk) for chunk in chunks],
    )


@router.post(
    "/{document_id}/ask",
    response_model=AskResponse,
    responses={
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Document has no embeddings yet"},
        502: {"model": ErrorResponse, "description": "Embedding, database or AI model failure"},
    },
)
def ask(
    document_id: uuid.UUID,
    body: AskRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AskResponse:
    """Answer a question from your document only (RAG), with the pages it
    was taken from. Waits for the complete answer; not saved to a
    conversation."""
    return AskResponse.model_validate(answer_question(db, user.id, document_id, body.question))


@router.post(
    "/{document_id}/summary",
    response_model=DocumentResponse,
    responses={
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Document is not processed yet"},
        502: {"model": ErrorResponse, "description": "AI model or database failure"},
    },
)
def generate_summary(
    document_id: uuid.UUID,
    body: GenerateRequest | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Generate (or regenerate) the document's summary from its full text
    and store it. Returns the document with `summary` filled in. Long
    documents take longer: they are summarized part by part."""
    language = body.language if body else None
    return DocumentResponse.model_validate(summarize_document(db, user.id, document_id, language))


@router.post(
    "/{document_id}/questions",
    response_model=DocumentResponse,
    responses={
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Document is not processed yet"},
        502: {"model": ErrorResponse, "description": "AI model or database failure"},
    },
)
def suggest_questions(
    document_id: uuid.UUID,
    body: GenerateRequest | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Generate (or regenerate) questions specific to this document, from
    its summary (if any) and excerpts spread across it, and store them.
    Returns the document with `questions` filled in."""
    language = body.language if body else None
    return DocumentResponse.model_validate(generate_questions(db, user.id, document_id, language))
