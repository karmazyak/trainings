"""Наивный инжест документов (обратная совместимость). Для книг используй preprocessor.py."""

import logging
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentChunk
from app.rag.embeddings import embed_texts

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


def extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif suffix == ".txt":
        return file_path.read_text(encoding="utf-8")
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def split_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - CHUNK_OVERLAP
    return chunks


async def ingest_document(file_path: Path, db: AsyncSession) -> int:
    """Наивный инжест (без LLM-обогащения). Для книг используй preprocess_and_ingest."""
    logger.info(f"Ingesting {file_path.name}")

    text = extract_text(file_path)
    chunks = split_text(text)

    if not chunks:
        return 0

    embeddings = embed_texts(chunks)

    for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
        db_chunk = DocumentChunk(
            document_name=file_path.name,
            chunk_index=i,
            content=chunk_text,
            embedding=embedding,
            domain="general",
        )
        db.add(db_chunk)

    await db.flush()

    # Заполняем search_vector
    await db.execute(
        sa_text(
            "UPDATE document_chunks "
            "SET search_vector = to_tsvector('russian', content) "
            "WHERE document_name = :source AND search_vector IS NULL"
        ),
        {"source": file_path.name},
    )

    await db.commit()
    logger.info(f"Ingested {len(chunks)} chunks from {file_path.name}")
    return len(chunks)
