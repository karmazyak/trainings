"""Роутер-агент: автоматически определяет, к какому специалисту направить запрос."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import llm_call_cheap, RetrievedChunk
from app.agents.trainer import trainer_agent
from app.agents.dietologist import dietologist_agent

logger = logging.getLogger(__name__)

ROUTER_PROMPT = (
    "Определи, к какому специалисту направить запрос пользователя.\n\n"
    "Варианты:\n"
    '- "trainer" — вопросы о тренировках, упражнениях, программах, технике, восстановлении, разминке\n'
    '- "dietologist" — вопросы о питании, диетах, рационах, КБЖУ, продуктах, добавках, водном балансе\n'
    '- "both" — запрос требует совместной работы (например: "составь мне программу тренировок и питание на неделю")\n\n'
    "Запрос: {user_message}\n\n"
    "Ответь ОДНИМ СЛОВОМ: trainer, dietologist или both."
)


async def route_message(user_message: str) -> str:
    """Определить, к какому агенту направить запрос. Возвращает 'trainer', 'dietologist' или 'both'."""
    prompt = ROUTER_PROMPT.format(user_message=user_message)
    messages = [{"role": "user", "content": prompt}]
    result = await llm_call_cheap(messages, temperature=0.0)
    result = result.strip().lower().strip('"').strip("'")

    if result not in ("trainer", "dietologist", "both"):
        logger.warning(f"Router returned unexpected value: {result!r}, defaulting to 'trainer'")
        if "diet" in result or "nutri" in result or "питан" in result:
            return "dietologist"
        if "both" in result or "оба" in result:
            return "both"
        return "trainer"

    return result


async def handle_both(
    user_message: str,
    db: AsyncSession,
    history: list[dict] | None = None,
    user_context: str = "",
    preferences: str = "",
) -> tuple[str, str, list[RetrievedChunk]]:
    """Обработка запроса, требующего обоих специалистов.

    1. Тренер составляет тренировочный план
    2. Диетолог получает этот план как контекст и составляет питание

    Returns:
        (combined_response, agent_used, sources)
    """
    # 1. Тренер
    trainer_text, trainer_sources = await trainer_agent.get_response(
        user_message=user_message,
        db=db,
        history=history,
        user_context=user_context,
        preferences=preferences,
    )

    # 2. Диетолог получает тренировочный план как дополнительный контекст
    diet_message = (
        f"{user_message}\n\n"
        f"Тренировочный план от тренера (учитывай его при составлении питания):\n"
        f"{trainer_text}"
    )
    diet_text, diet_sources = await dietologist_agent.get_response(
        user_message=diet_message,
        db=db,
        history=history,
        user_context=user_context,
        preferences=preferences,
    )

    combined = (
        "## 🏋️ Тренировочный план\n\n"
        f"{trainer_text}\n\n"
        "---\n\n"
        "## 🥗 План питания\n\n"
        f"{diet_text}"
    )

    all_sources = trainer_sources + diet_sources
    return combined, "both", all_sources
