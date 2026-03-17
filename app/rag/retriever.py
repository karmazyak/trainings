"""Гибридный RAG-ретривер: семантический + ключевой поиск + RRF + реренкинг."""

import json
import logging

from pydantic import BaseModel
from sqlalchemy import select, text, func, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import DocumentChunk
from app.rag.embeddings import embed_query

logger = logging.getLogger(__name__)

RRF_K = 60  # параметр Reciprocal Rank Fusion


class RetrievedChunk(BaseModel):
    """Результат поиска с метаданными."""
    content: str
    source: str
    chapter: str | None = None
    domain: str | None = None
    score: float = 0.0


async def _semantic_search(
    query_embedding: list[float],
    db: AsyncSession,
    domain_filter: list[str] | None = None,
    limit: int = 20,
) -> list[tuple[DocumentChunk, int]]:
    """Семантический поиск по cosine distance. Возвращает (chunk, rank)."""
    stmt = (
        select(DocumentChunk)
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
    )
    if domain_filter:
        stmt = stmt.where(DocumentChunk.domain.in_(domain_filter))
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    chunks = result.scalars().all()
    return [(chunk, rank) for rank, chunk in enumerate(chunks)]


async def _keyword_search(
    query: str,
    db: AsyncSession,
    domain_filter: list[str] | None = None,
    limit: int = 20,
) -> list[tuple[DocumentChunk, int]]:
    """Ключевой поиск по PostgreSQL full-text search. Возвращает (chunk, rank)."""
    # Поиск по русскому и английскому — plainto_tsquery с обоими
    ts_query = func.plainto_tsquery("russian", query)

    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.search_vector.isnot(None))
        .where(DocumentChunk.search_vector.op("@@")(ts_query))
        .order_by(
            func.ts_rank(DocumentChunk.search_vector, ts_query).desc()
        )
    )
    if domain_filter:
        stmt = stmt.where(DocumentChunk.domain.in_(domain_filter))
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    chunks = result.scalars().all()
    return [(chunk, rank) for rank, chunk in enumerate(chunks)]


def _rrf_merge(
    semantic_results: list[tuple[DocumentChunk, int]],
    keyword_results: list[tuple[DocumentChunk, int]],
    top_k: int,
) -> list[DocumentChunk]:
    """Объединение результатов через Reciprocal Rank Fusion."""
    scores: dict[str, float] = {}
    chunk_map: dict[str, DocumentChunk] = {}

    for chunk, rank in semantic_results:
        chunk_id = str(chunk.id)
        scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (RRF_K + rank)
        chunk_map[chunk_id] = chunk

    for chunk, rank in keyword_results:
        chunk_id = str(chunk.id)
        scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (RRF_K + rank)
        chunk_map[chunk_id] = chunk

    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:top_k]
    return [chunk_map[cid] for cid in sorted_ids]


async def _rerank(
    query: str,
    chunks: list[DocumentChunk],
    top_k: int = 5,
) -> list[DocumentChunk]:
    """Реренкинг через LLM: выбираем наиболее релевантные чанки."""
    from app.agents.base import llm_call_cheap

    fragments = []
    for i, chunk in enumerate(chunks):
        text_preview = chunk.content[:300]
        fragments.append(f"[{i}]: {text_preview}")

    prompt = (
        f"Запрос пользователя: {query}\n\n"
        f"Фрагменты:\n" + "\n".join(fragments) + "\n\n"
        f"Отранжируй фрагменты по релевантности к запросу. "
        f"Верни JSON-массив индексов от наиболее релевантного к наименее: [3, 1, 5, ...]"
    )

    try:
        result = await llm_call_cheap([{"role": "user", "content": prompt}], temperature=0.0)
        # Парсим JSON-массив индексов
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        indices = json.loads(result)
        reranked = []
        seen = set()
        for idx in indices[:top_k]:
            if isinstance(idx, int) and 0 <= idx < len(chunks) and idx not in seen:
                reranked.append(chunks[idx])
                seen.add(idx)
        # Добавляем оставшиеся если реренкинг вернул мало
        for i, chunk in enumerate(chunks):
            if len(reranked) >= top_k:
                break
            if i not in seen:
                reranked.append(chunk)
        return reranked[:top_k]
    except Exception as e:
        logger.warning(f"Reranking failed: {e}, falling back to RRF order")
        return chunks[:top_k]


async def retrieve_context(
    query: str,
    db: AsyncSession,
    domain_filter: list[str] | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Гибридный поиск: семантический + ключевой + RRF + опциональный реренкинг."""
    top_k = top_k or settings.rag_top_k
    query_embedding = embed_query(query)

    # Параллельные запросы
    semantic = await _semantic_search(query_embedding, db, domain_filter, limit=20)
    keyword = await _keyword_search(query, db, domain_filter, limit=20)

    # RRF merge
    merged = _rrf_merge(semantic, keyword, top_k=20)

    if not merged:
        # Fallback: только семантический
        merged = [chunk for chunk, _ in semantic[:top_k]]

    # Реренкинг
    if settings.rag_use_reranking and len(merged) > top_k:
        final = await _rerank(query, merged, top_k=top_k)
    else:
        final = merged[:top_k]

    return [
        RetrievedChunk(
            content=chunk.content,
            source=chunk.document_name,
            chapter=chunk.chapter,
            domain=chunk.domain,
        )
        for chunk in final
    ]
