import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.dietologist import dietologist_agent
from app.agents.router import handle_both, route_message
from app.agents.trainer import trainer_agent
from app.database import get_db
from app.models import User, Conversation, Message
from app.rag.retriever import RetrievedChunk
from app.schemas import AgentType, ChatRequest, ChatResponse, SourceReference
from app.services.preferences import (
    compress_plan,
    extract_memory_from_conversation,
    format_preferences_for_prompt,
    get_other_agent_plan,
    get_user_preferences,
    save_agent_plan,
    save_preferences,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

AGENTS = {
    "trainer": trainer_agent,
    "dietologist": dietologist_agent,
}


def format_user_context(user: User) -> str:
    """Форматировать профиль пользователя для системного промпта агента."""
    parts = []
    if user.name:
        parts.append(f"Имя: {user.name}")
    if user.age:
        parts.append(f"Возраст: {user.age}")
    if user.gender:
        parts.append(f"Пол: {user.gender}")
    if user.height_cm:
        parts.append(f"Рост: {user.height_cm} см")
    if user.weight_kg:
        parts.append(f"Вес: {user.weight_kg} кг")
    if user.goal:
        parts.append(f"Цель: {user.goal}")
    if user.fitness_level:
        parts.append(f"Уровень подготовки: {user.fitness_level}")
    if user.training_style:
        style_labels = {
            "gym": "Тренировки в зале (штанги, тренажёры, гантели)",
            "home": "Домашние тренировки (собственный вес, гантели, резинки)",
            "crossfit": "Кроссфит / функциональный тренинг (WOD, AMRAP, EMOM)",
            "running": "Бег, растяжка, йога, кардио",
        }
        parts.append(f"Стиль тренировок: {style_labels.get(user.training_style, user.training_style)}")
    if user.activity_level:
        parts.append(f"Уровень активности: {user.activity_level}")
    if user.limitations:
        parts.append(f"Ограничения/травмы: {user.limitations}")
    if user.dietary_restrictions:
        parts.append(f"Ограничения в питании: {user.dietary_restrictions}")
    if user.allergies:
        parts.append(f"Аллергии: {user.allergies}")
    return "\n".join(parts)


def _build_sources(chunks: list[RetrievedChunk]) -> list[SourceReference]:
    """Уникальные источники из RAG-чанков."""
    seen = set()
    sources = []
    for chunk in chunks:
        key = (chunk.source, chunk.chapter)
        if key not in seen:
            seen.add(key)
            sources.append(SourceReference(
                book=chunk.source,
                chapter=chunk.chapter,
            ))
    return sources


@router.post("", response_model=ChatResponse)
async def chat(data: ChatRequest, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Определяем агента
    if data.agent == AgentType.auto:
        agent_key = await route_message(data.message)
    else:
        agent_key = data.agent.value

    # Создаём / загружаем conversation
    if data.conversation_id:
        conversation = await db.get(Conversation, data.conversation_id)
        if not conversation or conversation.user_id != user.id:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = Conversation(user_id=user.id, agent_type=agent_key)
        db.add(conversation)
        await db.flush()

    # Загружаем историю
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    )
    result = await db.execute(stmt)
    db_messages = result.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in db_messages]

    user_context = format_user_context(user)

    # Load user preferences and cross-agent plan
    prefs = await get_user_preferences(db, user.id)
    prefs_text = format_preferences_for_prompt(prefs)

    # Выбираем путь обработки
    if agent_key == "both":
        response_text, agent_used, chunks = await handle_both(
            user_message=data.message,
            db=db,
            history=history,
            user_context=user_context,
            preferences=prefs_text,
        )
    else:
        other_plan = await get_other_agent_plan(db, user.id, agent_key)
        agent = AGENTS[agent_key]
        response_text, chunks = await agent.get_response(
            user_message=data.message,
            db=db,
            history=history,
            user_context=user_context,
            preferences=prefs_text,
            other_agent_plan=other_plan,
        )
        agent_used = agent_key

    # Сохраняем сообщения
    db.add(Message(conversation_id=conversation.id, role="user", content=data.message))
    assistant_msg = Message(conversation_id=conversation.id, role="assistant", content=response_text)
    db.add(assistant_msg)
    await db.flush()

    # Save plan summary for cross-agent coordination (best-effort)
    if agent_key in ("trainer", "dietologist") and len(response_text) > 200:
        try:
            summary = await compress_plan(response_text, agent_key)
            if summary:
                await save_agent_plan(db, user.id, agent_key, summary)
        except Exception:
            logger.exception("Failed to save plan summary")

    # Extract and save user memory from conversation (best-effort)
    try:
        facts = await extract_memory_from_conversation(data.message, response_text)
        if facts:
            await save_preferences(db, user.id, facts)
            logger.info("Learned %d facts about user %s: %s",
                        len(facts), user.name, [f["key"] for f in facts])
    except Exception:
        logger.debug("Memory extraction skipped")

    await db.commit()

    return ChatResponse(
        conversation_id=conversation.id,
        agent_used=agent_used,
        message=response_text,
        message_db_id=assistant_msg.id,
        sources=_build_sources(chunks),
    )
