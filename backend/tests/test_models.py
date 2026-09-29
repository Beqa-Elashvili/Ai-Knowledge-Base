from pgvector.sqlalchemy import Vector

from app.models import EMBEDDING_DIMENSIONS, Base, DocumentChunk


def test_all_tables_are_mapped() -> None:
    assert set(Base.metadata.tables) == {"documents", "document_chunks", "conversations", "messages"}


def test_embedding_is_1536_dimensional_vector() -> None:
    column = DocumentChunk.__table__.c.embedding
    assert isinstance(column.type, Vector)
    assert column.type.dim == EMBEDDING_DIMENSIONS == 1536


def test_chunks_keep_page_range_metadata() -> None:
    columns = DocumentChunk.__table__.c
    for name in ("document_id", "page_number", "page_end", "chunk_index"):
        assert not columns[name].nullable, name


def test_child_rows_cascade_with_parent() -> None:
    for table, fk_target in [("document_chunks", "documents"), ("conversations", "documents"), ("messages", "conversations")]:
        fks = Base.metadata.tables[table].foreign_keys
        assert any(fk.column.table.name == fk_target and fk.ondelete == "CASCADE" for fk in fks), table

