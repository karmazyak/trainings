import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.dietologist import dietologist_agent
from app.agents.router import handle_both, route_message
from app.agents.trainer import trainer_agent
from app.database import get_db
from app.models import User, Conversation, Message
from app.rag.retriever import RetrievedChunk
from app.schemas import AgentType, ChatRequest, ChatResponse, SituationRequest, SourceReference, TryQuestionRequest, TryQuestionResponse
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

# Import session factory for background tasks
from app.database import async_session


async def _extract_memory_background(user_id: UUID, user_name: str, user_message: str, response_text: str):
    """Extract and save user memory from conversation in background."""
    try:
        facts = await extract_memory_from_conversation(user_message, response_text)
        if facts:
            async with async_session() as db:
                await save_preferences(db, user_id, facts)
                await db.commit()
            logger.info("Learned %d facts about user %s: %s",
                        len(facts), user_name, [f["key"] for f in facts])
    except Exception:
        logger.warning("Memory extraction failed")

AGENTS = {
    "trainer": trainer_agent,
    "dietologist": dietologist_agent,
}


async def format_user_context(user: User, db: AsyncSession | None = None) -> str:
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

    # v2: Load weekly schedule from WeekScheduleSlot
    if db:
        from app.models import WeekScheduleSlot, ExerciseLog
        stmt = select(WeekScheduleSlot).where(WeekScheduleSlot.user_id == user.id).order_by(WeekScheduleSlot.day_of_week)
        result = await db.execute(stmt)
        slots = result.scalars().all()
        if slots:
            day_names = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
            type_labels = {
                "gym": "🏋️ Зал", "home": "🏠 Дома", "run": "🏃 Бег",
                "yoga": "🧘 Йога", "sport": "⚽ Спорт", "rest": "😴 Отдых",
            }
            schedule_str = " | ".join(
                f"{day_names.get(s.day_of_week, '?')} {type_labels.get(s.activity_type, s.activity_type)}"
                for s in slots
            )
            parts.append(f"Расписание недели: {schedule_str}")
        elif user.training_style:
            style_labels = {
                "gym": "Тренировки в зале", "home": "Домашние тренировки",
                "crossfit": "Кроссфит", "running": "Бег, йога, кардио",
                "run": "Бег", "yoga": "Йога",
            }
            parts.append(f"Стиль тренировок: {style_labels.get(user.training_style, user.training_style)}")

        # v2: Load recent exercise history for weight progression
        from sqlalchemy import distinct
        stmt = (
            select(ExerciseLog)
            .where(ExerciseLog.user_id == user.id)
            .order_by(ExerciseLog.logged_at.desc(), ExerciseLog.created_at.desc())
            .limit(20)
        )
        result = await db.execute(stmt)
        logs = result.scalars().all()
        if logs:
            seen = set()
            log_parts = []
            for log in logs:
                if log.exercise_name not in seen and len(seen) < 5:
                    seen.add(log.exercise_name)
                    log_parts.append(f"  {log.exercise_label}: {log.weight_kg}кг × {log.reps} × {log.sets} ({log.logged_at})")
            if log_parts:
                parts.append("История весов:\n" + "\n".join(log_parts))
    elif user.training_style:
        style_labels = {
            "gym": "Тренировки в зале", "home": "Домашние тренировки",
            "crossfit": "Кроссфит", "running": "Бег, йога, кардио",
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
    if user.preferred_training_days:
        day_names = {
            "1": "Пн", "2": "Вт", "3": "Ср", "4": "Чт",
            "5": "Пт", "6": "Сб", "7": "Вс",
        }
        days = [day_names.get(d.strip(), d.strip()) for d in user.preferred_training_days.split(",")]
        parts.append(f"Дни тренировок: {', '.join(days)}")
    if user.test_pushups is not None or user.test_plank_sec is not None or user.test_squats is not None:
        test_parts = []
        if user.test_pushups is not None:
            test_parts.append(f"отжимания: {user.test_pushups} раз")
        if user.test_plank_sec is not None:
            test_parts.append(f"планка: {user.test_plank_sec} сек")
        if user.test_squats is not None:
            test_parts.append(f"приседания: {user.test_squats} раз")
        parts.append(f"Фитнес-тест: {', '.join(test_parts)}")
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


async def _update_workout_cache(db: AsyncSession, user: User, response_text: str):
    """Update cached workout_week plan and re-populate sessions from a chat response."""
    from datetime import date
    from app.models import CachedPlan, TrainingSession
    from sqlalchemy import select, and_, delete

    today = date.today()
    iso = today.isocalendar()
    week, year = iso.week, iso.year

    # Update or create workout_week cache
    stmt = select(CachedPlan).where(
        and_(
            CachedPlan.user_id == user.id,
            CachedPlan.plan_type == "workout_week",
            CachedPlan.week_number == week,
            CachedPlan.year == year,
        )
    )
    result = await db.execute(stmt)
    old = result.scalar_one_or_none()
    if old:
        old.content = response_text
    else:
        db.add(CachedPlan(
            user_id=user.id,
            plan_type="workout_week",
            content=response_text,
            week_number=week,
            year=year,
        ))
    await db.flush()

    # Re-populate training sessions
    try:
        from app.routers.schedule import _parse_workout_week_into_sessions, _get_week_sessions

        existing = await _get_week_sessions(db, user.id, week, year)
        for s in existing:
            if s.status == "scheduled":  # Only delete unfinished sessions
                await db.delete(s)
        await db.flush()

        sessions = await _parse_workout_week_into_sessions(
            db, user, response_text, None, week, year,
        )
        for s in sessions:
            db.add(s)
        logger.info("Updated %d sessions from chat for user %s", len(sessions), user.id)
    except Exception:
        logger.exception("Failed to re-populate sessions from chat")


# Situation prompts for contextual nutrition help
SITUATION_PROMPTS = {
    "party": "Я на застолье/дне рождения. {user_kbju}. Дай конкретные советы: что есть, чего избегать, как не выйти за калории. Конкретно и кратко.",
    "shop": "Я в магазине, ищу {subcategory}. Моя цель: {goal}. Посоветуй конкретные продукты — что купить, чего избегать.",
    "delivery": "Хочу заказать еду (доставка). Моя цель: {goal}. Какие блюда выбрать, каких избегать?",
    "preworkout": "Собираюсь на тренировку ({today_activity}). Что поесть за 1-2 часа до?",
    "late_meal": "Поздний вечер, я голоден. {user_kbju}. Что съесть чтобы не навредить сну и не выйти за КБЖУ?",
}

SHOP_LABELS = {
    "meat": "мясо/рыбу", "dairy": "молочные продукты", "grain": "крупы/хлеб",
    "veg": "овощи/фрукты", "snack": "перекусы/снеки",
}


@router.post("/situation", response_model=ChatResponse)
async def chat_situation(data: SituationRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Build situation prompt
    goal = user.goal or "поддержание формы"
    kbju = f"Мой КБЖУ: цель {goal}"
    if user.weight_kg:
        kbju += f", вес {user.weight_kg}кг"

    # Get today's activity from schedule
    from app.models import WeekScheduleSlot
    from datetime import date as date_cls
    today_dow = date_cls.today().isoweekday()
    stmt = select(WeekScheduleSlot).where(WeekScheduleSlot.user_id == user.id, WeekScheduleSlot.day_of_week == today_dow)
    result = await db.execute(stmt)
    today_slot = result.scalar_one_or_none()
    today_activity = today_slot.activity_type if today_slot else (user.training_style or "тренировка")

    subcategory = SHOP_LABELS.get(data.subcategory, data.subcategory or "продукты")

    if data.situation in SITUATION_PROMPTS:
        prompt = SITUATION_PROMPTS[data.situation].format(
            user_kbju=kbju, goal=goal, today_activity=today_activity, subcategory=subcategory,
        )
    else:
        prompt = data.situation  # custom text

    user_context = await format_user_context(user, db)
    prefs = await get_user_preferences(db, user.id)
    prefs_text = format_preferences_for_prompt(prefs)

    # Get or create conversation
    conversation = None
    if data.conversation_id:
        conversation = await db.get(Conversation, data.conversation_id)
    if not conversation:
        conversation = Conversation(user_id=user.id, agent_type="dietologist")
        db.add(conversation)
        await db.flush()

    try:
        response_text, chunks = await dietologist_agent.get_response(
            user_message=prompt, db=db, history=[], user_context=user_context, preferences=prefs_text,
        )
    except Exception:
        logger.exception("Situation chat failed for user %s", user.id)
        raise HTTPException(status_code=503, detail="AI temporarily unavailable")

    db.add(Message(conversation_id=conversation.id, role="user", content=prompt))
    assistant_msg = Message(conversation_id=conversation.id, role="assistant", content=response_text)
    db.add(assistant_msg)
    await db.commit()

    return ChatResponse(
        conversation_id=conversation.id,
        agent_used="dietologist",
        message=response_text,
        message_db_id=assistant_msg.id,
        sources=_build_sources(chunks),
    )


@router.post("/try", response_model=TryQuestionResponse)
async def chat_try(data: TryQuestionRequest, db: AsyncSession = Depends(get_db)):
    """Answer a question without user registration — for onboarding aha moment."""
    from app.agents.base import llm_call
    from app.rag.retriever import retrieve_context

    chunks = await retrieve_context(query=data.message, db=db)

    rag_parts = []
    for chunk in chunks:
        source_info = f"[Источник: {chunk.source}"
        if chunk.chapter:
            source_info += f", {chunk.chapter}"
        source_info += "]"
        rag_parts.append(f"{source_info}\n{chunk.content}")
    rag_context = "\n\n---\n\n".join(rag_parts) if rag_parts else ""

    system = (
        "Ты — фитнес-эксперт. Отвечай кратко, конкретно и по делу. "
        "Основывай рекомендации на научных данных. "
        "Если в базе знаний есть источник — ОБЯЗАТЕЛЬНО ссылайся на него "
        "(формат: «📚 Источник: [название]»). "
        "ОТВЕЧАЙ ТОЛЬКО НА РУССКОМ ЯЗЫКЕ."
    )
    if rag_context:
        system += f"\n\n<knowledge_base>\n{rag_context}\n</knowledge_base>"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": data.message},
    ]
    response_text = await llm_call(messages)

    return TryQuestionResponse(
        message=response_text,
        sources=_build_sources(chunks),
    )


@router.post("", response_model=ChatResponse)
async def chat(data: ChatRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
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
    history = [{"role": m.role, "content": m.content} for m in db_messages[-20:]]

    user_context = await format_user_context(user, db)

    # Load user preferences and cross-agent plan
    prefs = await get_user_preferences(db, user.id)
    prefs_text = format_preferences_for_prompt(prefs)

    # Выбираем путь обработки
    try:
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
    except Exception:
        logger.exception("LLM call failed for user %s", user.id)
        raise HTTPException(status_code=503, detail="AI temporarily unavailable, please try again")

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

    # If trainer generated a long response (likely a new workout plan), update cache
    if agent_key == "trainer" and len(response_text) > 500:
        try:
            await _update_workout_cache(db, user, response_text)
        except Exception:
            logger.exception("Failed to update workout cache from chat")

    await db.commit()

    # Extract and save user memory in background (non-blocking)
    if len(data.message) >= 15:
        background_tasks.add_task(
            _extract_memory_background, user.id, user.name, data.message, response_text
        )

    return ChatResponse(
        conversation_id=conversation.id,
        agent_used=agent_used,
        message=response_text,
        message_db_id=assistant_msg.id,
        sources=_build_sources(chunks),
    )
