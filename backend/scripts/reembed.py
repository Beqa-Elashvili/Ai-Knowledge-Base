"""(Re)generate chunk embeddings with the configured provider.

Usage (from backend/, venv active):
    python -m scripts.reembed          # only chunks without an embedding
    python -m scripts.reembed --all    # every chunk (after changing
                                       # EMBEDDING_PROVIDER or EMBEDDING_MODEL)

Works one document at a time, each in its own transaction: a document's
chunks are either all updated or left as they were. A document whose chunks
all have embeddings afterwards is marked "ready".
"""

import argparse
import logging
import sys

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.errors import AppError
from app.models import Document, DocumentChunk
from app.services.embeddings import embed_documents

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("reembed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="re-embed every chunk, not only missing ones")
    args = parser.parse_args()

    settings = get_settings()
    logger.info("Provider=%s model=%s", settings.embedding_provider, settings.resolved_embedding_model)

    with Session(get_engine()) as db:
        missing = select(DocumentChunk.document_id).where(DocumentChunk.embedding.is_(None))
        stmt = select(Document.id, Document.title).order_by(Document.created_at)
        if not args.all:
            stmt = stmt.where(Document.id.in_(missing))
        documents = db.execute(stmt).all()

    if not documents:
        logger.info("Nothing to do: every chunk already has an embedding.")
        return 0

    failed = 0
    for document_id, title in documents:
        with Session(get_engine()) as db:
            stmt = select(DocumentChunk.id, DocumentChunk.content).where(DocumentChunk.document_id == document_id)
            if not args.all:
                stmt = stmt.where(DocumentChunk.embedding.is_(None))
            chunks = db.execute(stmt.order_by(DocumentChunk.chunk_index)).all()
            try:
                vectors = embed_documents([content for _, content in chunks])
            except AppError as exc:
                failed += 1
                logger.error("Skipped %r (%s): %s", title, document_id, exc.message)
                continue
            for (chunk_id, _), vector in zip(chunks, vectors, strict=True):
                db.execute(update(DocumentChunk).where(DocumentChunk.id == chunk_id).values(embedding=vector))
            db.execute(update(Document).where(Document.id == document_id).values(status="ready"))
            db.commit()
            logger.info("Embedded %d chunk(s) of %r", len(chunks), title)

    logger.info("Done: %d document(s) updated, %d failed.", len(documents) - failed, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
