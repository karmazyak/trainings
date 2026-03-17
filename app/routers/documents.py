import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, func, delete, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import DocumentChunk
from app.rag.ingest import ingest_document
from app.rag.preprocessor import preprocess_and_ingest
from app.schemas import DocumentUploadResponse, DocumentStatsResponse, IngestFolderResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".epub"}
BOOKS_DIR = Path("books")


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Простая загрузка документа (наивное разбиение, обратная совместимость)."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".txt"):
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        chunks_count = await ingest_document(tmp_path, db)
    finally:
        tmp_path.unlink(missing_ok=True)

    return DocumentUploadResponse(
        document_name=file.filename,
        chunks_count=chunks_count,
    )


@router.post("/upload-book", response_model=DocumentUploadResponse)
async def upload_book(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Загрузка книги с полной интеллектуальной предобработкой."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        chunks_count = await preprocess_and_ingest(tmp_path, db)
    finally:
        tmp_path.unlink(missing_ok=True)

    return DocumentUploadResponse(
        document_name=file.filename,
        chunks_count=chunks_count,
    )


@router.post("/ingest-folder", response_model=IngestFolderResponse)
async def ingest_folder(
    db: AsyncSession = Depends(get_db),
):
    """Обработать все файлы из папки books/."""
    if not BOOKS_DIR.exists():
        raise HTTPException(status_code=404, detail="books/ directory not found")

    processed = []
    errors = []

    for file_path in sorted(BOOKS_DIR.iterdir()):
        if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue

        # Проверяем, не загружена ли уже эта книга
        existing = await db.execute(
            select(func.count()).where(DocumentChunk.document_name == file_path.name)
        )
        if existing.scalar() > 0:
            logger.info(f"Skipping {file_path.name}: already ingested")
            continue

        try:
            chunks_count = await preprocess_and_ingest(file_path, db)
            processed.append(DocumentUploadResponse(
                document_name=file_path.name,
                chunks_count=chunks_count,
            ))
        except Exception as e:
            logger.error(f"Failed to ingest {file_path.name}: {e}")
            errors.append(f"{file_path.name}: {str(e)}")

    return IngestFolderResponse(processed=processed, errors=errors)


@router.get("/stats", response_model=DocumentStatsResponse)
async def document_stats(
    db: AsyncSession = Depends(get_db),
):
    """Статистика по загруженным документам."""
    # Общее количество чанков
    total = await db.execute(select(func.count(DocumentChunk.id)))
    total_chunks = total.scalar()

    # По доменам
    domain_rows = await db.execute(
        select(DocumentChunk.domain, func.count())
        .group_by(DocumentChunk.domain)
    )
    by_domain = {row[0] or "unknown": row[1] for row in domain_rows}

    # По источникам
    source_rows = await db.execute(
        select(DocumentChunk.document_name, func.count())
        .group_by(DocumentChunk.document_name)
    )
    by_source = {row[0]: row[1] for row in source_rows}

    return DocumentStatsResponse(
        total_chunks=total_chunks,
        by_domain=by_domain,
        by_source=by_source,
    )


@router.delete("/{source}")
async def delete_document(
    source: str,
    db: AsyncSession = Depends(get_db),
):
    """Удалить все чанки конкретной книги."""
    result = await db.execute(
        delete(DocumentChunk).where(DocumentChunk.document_name == source)
    )
    await db.commit()
    deleted = result.rowcount
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Document '{source}' not found")
    return {"deleted_chunks": deleted, "document_name": source}
