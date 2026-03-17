"""Умная предобработка книг: извлечение → очистка → чанкирование → обогащение → классификация."""

import asyncio
import json
import logging
import re
from pathlib import Path

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import llm_call_cheap
from app.models import DocumentChunk
from app.rag.embeddings import embed_texts

logger = logging.getLogger(__name__)

CHUNK_SIZE = 2000  # ~512 токенов
CHUNK_OVERLAP = 200  # ~50 токенов
ENRICHMENT_BATCH_SIZE = 5
DOC_PREVIEW_SIZE = 5000


# ── 1. Извлечение текста ─────────────────────────────


def extract_text(file_path: Path) -> str:
    """Извлечь текст из файла (PDF, TXT, MD, EPUB)."""
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(file_path)
    elif suffix in (".txt", ".md"):
        return file_path.read_text(encoding="utf-8")
    elif suffix == ".epub":
        return _extract_epub(file_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def _extract_pdf(file_path: Path) -> str:
    """Извлечение текста из PDF через pymupdf (fitz)."""
    import fitz  # pymupdf

    doc = fitz.open(str(file_path))
    pages = []
    for page in doc:
        page_text = page.get_text("text")
        if page_text:
            pages.append(page_text)
    doc.close()
    return "\n\n".join(pages)


def _extract_epub(file_path: Path) -> str:
    """Извлечение текста из EPUB через ebooklib + BeautifulSoup."""
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    book = epub.read_epub(str(file_path), options={"ignore_ncx": True})
    chapters = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text(separator="\n")
        if text.strip():
            chapters.append(text.strip())
    return "\n\n".join(chapters)


# ── 2. Очистка текста ────────────────────────────────


def clean_text(text: str) -> str:
    """Очистка текста от мусора: номера страниц, колонтитулы, лишние пробелы."""
    # Убираем номера страниц (отдельные числа на строке)
    text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)
    # Убираем множественные пустые строки (оставляем максимум 2)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    # Убираем множественные пробелы внутри строки
    text = re.sub(r"[ \t]{3,}", "  ", text)
    # Убираем строки состоящие только из спецсимволов
    text = re.sub(r"^[=\-_]{3,}$", "", text, flags=re.MULTILINE)
    return text.strip()


# ── 3. Определение глав ──────────────────────────────


def detect_chapters(text: str) -> list[tuple[str, str]]:
    """Разбить текст на главы. Возвращает [(chapter_title, chapter_text), ...]."""
    # Ищем заголовки глав (markdown-стиль или типичные паттерны)
    chapter_patterns = [
        r"^(#{1,3}\s+.+)$",  # Markdown headers
        r"^(Глава\s+\d+[.:]\s*.+)$",  # "Глава 1: ..."
        r"^(Chapter\s+\d+[.:]\s*.+)$",  # "Chapter 1: ..."
        r"^(ГЛАВА\s+\d+[.:]\s*.+)$",  # "ГЛАВА 1: ..."
        r"^(Часть\s+\d+[.:]\s*.+)$",  # "Часть 1: ..."
        r"^(Раздел\s+\d+[.:]\s*.+)$",  # "Раздел 1: ..."
    ]

    combined_pattern = "|".join(f"(?:{p})" for p in chapter_patterns)
    matches = list(re.finditer(combined_pattern, text, re.MULTILINE))

    if not matches:
        return [("", text)]

    chapters = []
    for i, match in enumerate(matches):
        title = match.group(0).strip().lstrip("#").strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chapter_text = text[start:end].strip()
        if chapter_text:
            chapters.append((title, chapter_text))

    # Текст до первой главы
    before_first = text[: matches[0].start()].strip()
    if before_first and len(before_first) > 100:
        chapters.insert(0, ("Введение", before_first))

    return chapters


# ── 4. Структурное чанкирование ──────────────────────


def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Структурное разбиение текста на чанки с приоритетом разделителей."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        separators=["\n# ", "\n## ", "\n### ", "\n\n", "\n", ". ", " "],
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        length_function=len,
    )
    chunks = splitter.split_text(text)
    return [c.strip() for c in chunks if c.strip()]


# ── 5. Контекстуальное обогащение ────────────────────


async def enrich_chunks(
    chunks: list[str],
    doc_preview: str,
) -> list[str]:
    """Для каждого чанка генерируем контекстный префикс через LLM (батчами)."""
    context_prefixes: list[str] = [""] * len(chunks)

    for batch_start in range(0, len(chunks), ENRICHMENT_BATCH_SIZE):
        batch_end = min(batch_start + ENRICHMENT_BATCH_SIZE, len(chunks))
        batch = chunks[batch_start:batch_end]

        tasks = [
            _generate_context(doc_preview, chunk)
            for chunk in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            idx = batch_start + i
            if isinstance(result, Exception):
                logger.warning(f"Context generation failed for chunk {idx}: {result}")
                context_prefixes[idx] = ""
            else:
                context_prefixes[idx] = result

    return context_prefixes


async def _generate_context(doc_preview: str, chunk_text: str) -> str:
    """Генерация контекстного префикса для одного чанка."""
    prompt = (
        f"<document>\n{doc_preview}\n</document>\n"
        f"<chunk>\n{chunk_text[:1000]}\n</chunk>\n"
        "Дай краткое пояснение (1-2 предложения), которое помещает этот фрагмент в контекст всего документа.\n"
        "Укажи: из какой книги/главы это, о чём именно идёт речь, для кого предназначена информация.\n"
        "Отвечай ТОЛЬКО контекстом, без преамбул."
    )
    return await llm_call_cheap([{"role": "user", "content": prompt}])


# ── 6. Тематическая классификация ────────────────────


async def classify_chunks(chunks: list[str]) -> list[dict]:
    """Классификация чанков по domain и topic_tags (батчами)."""
    results: list[dict] = [{"domain": "general", "topic_tags": []}] * len(chunks)

    for batch_start in range(0, len(chunks), ENRICHMENT_BATCH_SIZE):
        batch_end = min(batch_start + ENRICHMENT_BATCH_SIZE, len(chunks))
        batch = chunks[batch_start:batch_end]

        fragments = []
        for i, chunk in enumerate(batch):
            fragments.append(f"[{i}]: {chunk[:300]}")

        prompt = (
            "Классифицируй каждый фрагмент текста. Для каждого верни JSON:\n"
            '{"chunk_index": N, "domain": "training|nutrition|health|general", '
            '"topic_tags": ["тег1", "тег2"]}\n\n'
            "Фрагменты:\n" + "\n".join(fragments) + "\n\n"
            "Ответь ТОЛЬКО валидным JSON-массивом."
        )

        try:
            response = await llm_call_cheap([{"role": "user", "content": prompt}], temperature=0.0)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(response)

            for item in parsed:
                idx = item.get("chunk_index", -1)
                if 0 <= idx < len(batch):
                    global_idx = batch_start + idx
                    results[global_idx] = {
                        "domain": item.get("domain", "general"),
                        "topic_tags": item.get("topic_tags", []),
                    }
        except Exception as e:
            logger.warning(f"Classification failed for batch {batch_start}: {e}")

    return results


# ── Основной пайплайн ────────────────────────────────


async def preprocess_and_ingest(
    file_path: Path,
    db: AsyncSession,
) -> int:
    """Полный пайплайн предобработки книги. Возвращает количество сохранённых чанков."""
    source_name = file_path.name
    logger.info(f"[{source_name}] Step 1/6: Extraction")
    raw_text = extract_text(file_path)
    if not raw_text.strip():
        logger.warning(f"[{source_name}] Empty text, skipping")
        return 0

    logger.info(f"[{source_name}] Step 2/6: Cleaning ({len(raw_text)} chars)")
    clean = clean_text(raw_text)

    doc_preview = clean[:DOC_PREVIEW_SIZE]

    logger.info(f"[{source_name}] Step 3/6: Chunking")
    chapters = detect_chapters(clean)

    all_chunks: list[str] = []
    all_chapters: list[str] = []
    for chapter_title, chapter_text in chapters:
        chunks = split_into_chunks(chapter_text)
        all_chunks.extend(chunks)
        all_chapters.extend([chapter_title] * len(chunks))

    if not all_chunks:
        logger.warning(f"[{source_name}] No chunks produced, skipping")
        return 0

    logger.info(f"[{source_name}] Step 4/6: Enrichment ({len(all_chunks)} chunks)")
    context_prefixes = await enrich_chunks(all_chunks, doc_preview)

    logger.info(f"[{source_name}] Step 5/6: Classification")
    classifications = await classify_chunks(all_chunks)

    logger.info(f"[{source_name}] Step 6/6: Embedding & saving")
    # Эмбеддинг: context_prefix + "\n\n" + chunk_text
    texts_for_embedding = []
    for i, chunk in enumerate(all_chunks):
        prefix = context_prefixes[i] if context_prefixes[i] else ""
        combined = f"{prefix}\n\n{chunk}" if prefix else chunk
        texts_for_embedding.append(combined)

    embeddings = embed_texts(texts_for_embedding)

    for i, (chunk_text, embedding) in enumerate(zip(all_chunks, embeddings)):
        classification = classifications[i] if i < len(classifications) else {"domain": "general", "topic_tags": []}
        db_chunk = DocumentChunk(
            document_name=source_name,
            chunk_index=i,
            content=chunk_text,
            embedding=embedding,
            chapter=all_chapters[i] if all_chapters[i] else None,
            context_prefix=context_prefixes[i] if context_prefixes[i] else None,
            domain=classification.get("domain", "general"),
            topic_tags=classification.get("topic_tags", []),
            token_count=len(chunk_text) // 4,  # rough estimate
        )
        db.add(db_chunk)

    await db.flush()

    # Заполняем search_vector для full-text search
    await db.execute(
        sa_text(
            "UPDATE document_chunks "
            "SET search_vector = to_tsvector('russian', content) "
            "WHERE document_name = :source AND search_vector IS NULL"
        ),
        {"source": source_name},
    )

    await db.commit()
    logger.info(f"[{source_name}] Done: {len(all_chunks)} chunks saved")
    return len(all_chunks)
