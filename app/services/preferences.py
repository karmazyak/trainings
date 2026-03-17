"""Preference extraction and management service.

Uses cheap LLM to extract user preferences from feedback and conversations,
and compresses agent plans for cross-agent coordination.
"""

import json
import logging
import uuid
from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import llm_call_cheap
from app.models import UserPreference, AgentPlan

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = (
    "Проанализируй текст пользователя и извлеки его предпочтения в фитнесе и питании.\n"
    "Верни JSON-список (или пустой список [] если предпочтений нет):\n"
    '[{{"category": "training"|"nutrition"|"general", "key": "краткий_ключ_на_английском", '
    '"value": "описание на русском", "confidence": 0.0-1.0}}]\n\n'
    "Примеры ключей: dislikes_running, prefers_chicken, no_morning_workouts, "
    "likes_hiit, lactose_intolerant, prefers_home_workouts, too_hard, too_easy\n\n"
    "Текст: {text}\n"
    "Контекст (что агент ответил): {context}\n\n"
    "Только JSON, без пояснений."
)

# Prompt for extracting facts from conversation messages
MEMORY_EXTRACT_PROMPT = (
    "Проанализируй диалог пользователя с AI-тренером/нутрициологом.\n"
    "Извлеки НОВЫЕ ФАКТЫ о пользователе, которые стоит запомнить для будущих рекомендаций.\n\n"
    "Какие факты запоминать:\n"
    "- Физические особенности: травмы, боли, ограничения (\"болит колено\", \"грыжа поясницы\")\n"
    "- Пищевые предпочтения: любимые/нелюбимые продукты (\"не ем рыбу\", \"люблю творог\")\n"
    "- Режим: время тренировок, сна, работы (\"тренируюсь утром\", \"работаю ночью\")\n"
    "- Оборудование: что есть дома (\"есть гантели до 20 кг\", \"есть турник\")\n"
    "- Опыт: конкретные навыки (\"умею делать стойку на руках\", \"никогда не бегал\")\n"
    "- Цели: конкретные (\"хочу подтянуться 20 раз\", \"готовлюсь к марафону\")\n"
    "- Нелюбимые упражнения/активности (\"ненавижу берпи\", \"скучно на беговой\")\n\n"
    "НЕ запоминай:\n"
    "- Общие вопросы (\"сколько повторений?\") — это не факт о пользователе\n"
    "- То, что уже есть в профиле (цель, уровень, пол)\n"
    "- Временные состояния (\"сегодня устал\")\n\n"
    "Сообщение пользователя: {user_message}\n"
    "Ответ агента: {agent_response}\n\n"
    "Верни JSON-список фактов (или [] если новых фактов нет):\n"
    '[{{"category": "training"|"nutrition"|"general", '
    '"key": "краткий_ключ_english", '
    '"value": "факт на русском (1 предложение)", '
    '"confidence": 0.5-0.9}}]\n\n'
    "Только JSON, без пояснений."
)

COMPRESS_PROMPT = (
    "Сожми этот {agent_type_label} план до краткого резюме (максимум 150 слов). "
    "Сохрани ключевую информацию: упражнения/блюда, объёмы, дни, калории.\n\n"
    "План:\n{plan_text}\n\n"
    "Краткое резюме:"
)


async def extract_preferences(text: str, context: str = "") -> list[dict]:
    """Extract structured preferences from user text using cheap LLM."""
    prompt = EXTRACT_PROMPT.format(text=text, context=context[:500])
    messages = [{"role": "user", "content": prompt}]
    try:
        result = await llm_call_cheap(messages, temperature=0.1)
        # Parse JSON from response
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0]
        prefs = json.loads(result)
        if not isinstance(prefs, list):
            return []
        return [p for p in prefs if isinstance(p, dict) and "key" in p and "value" in p]
    except Exception:
        logger.exception("Failed to extract preferences")
        return []


async def save_preferences(
    db: AsyncSession, user_id: uuid.UUID, prefs: list[dict]
) -> None:
    """Upsert preferences — increase confidence if key already exists."""
    for pref in prefs:
        category = pref.get("category", "general")
        key = pref["key"]
        value = pref["value"]
        new_confidence = pref.get("confidence", 0.5)

        # Check if preference already exists
        stmt = select(UserPreference).where(
            and_(
                UserPreference.user_id == user_id,
                UserPreference.key == key,
            )
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Bump confidence (max 1.0)
            existing.confidence = min(1.0, existing.confidence + 0.15)
            existing.value = value
            existing.updated_at = datetime.utcnow()
        else:
            db.add(UserPreference(
                user_id=user_id,
                category=category,
                key=key,
                value=value,
                confidence=new_confidence,
            ))

    await db.flush()


async def get_user_preferences(
    db: AsyncSession, user_id: uuid.UUID, min_confidence: float = 0.3
) -> list[dict]:
    """Load user preferences with confidence above threshold."""
    stmt = (
        select(UserPreference)
        .where(
            and_(
                UserPreference.user_id == user_id,
                UserPreference.confidence >= min_confidence,
            )
        )
        .order_by(UserPreference.confidence.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    prefs = result.scalars().all()
    return [
        {"category": p.category, "key": p.key, "value": p.value, "confidence": p.confidence}
        for p in prefs
    ]


def format_preferences_for_prompt(prefs: list[dict]) -> str:
    """Format preferences list into text for agent system prompt.

    Groups by category and shows confidence level.
    High-confidence facts (>= 0.7) are marked as confirmed.
    """
    if not prefs:
        return ""

    # Group by category for readability
    by_cat: dict[str, list] = {}
    for p in prefs:
        cat = p.get("category", "general")
        by_cat.setdefault(cat, []).append(p)

    cat_labels = {
        "training": "Тренировки",
        "nutrition": "Питание",
        "general": "Общее",
    }

    lines = []
    for cat, items in by_cat.items():
        label = cat_labels.get(cat, cat)
        lines.append(f"[{label}]")
        for p in items:
            conf = "✓" if p["confidence"] >= 0.7 else "~"
            lines.append(f"  {conf} {p['value']}")

    return "\n".join(lines)


async def extract_memory_from_conversation(
    user_message: str, agent_response: str
) -> list[dict]:
    """Extract memorable facts from a conversation turn using cheap LLM.

    Called after every chat response to build up user memory over time.
    Returns empty list for generic questions with no personal info.
    """
    # Quick filter: skip very short or obviously generic messages
    if len(user_message) < 15:
        return []

    prompt = MEMORY_EXTRACT_PROMPT.format(
        user_message=user_message[:500],
        agent_response=agent_response[:500],
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        result = await llm_call_cheap(messages, temperature=0.1)
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0]
        facts = json.loads(result)
        if not isinstance(facts, list):
            return []
        return [f for f in facts if isinstance(f, dict) and "key" in f and "value" in f]
    except Exception:
        logger.debug("No memory extracted (this is normal for generic messages)")
        return []


async def compress_plan(plan_text: str, agent_type: str) -> str:
    """Compress a full plan to ~150 word summary for cross-agent sharing."""
    label = "тренировочный" if agent_type == "trainer" else "питания"
    prompt = COMPRESS_PROMPT.format(agent_type_label=label, plan_text=plan_text[:3000])
    messages = [{"role": "user", "content": prompt}]
    try:
        return await llm_call_cheap(messages, temperature=0.2)
    except Exception:
        logger.exception("Failed to compress plan")
        return ""


async def save_agent_plan(
    db: AsyncSession, user_id: uuid.UUID, agent_type: str, plan_summary: str
) -> None:
    """Save or update the latest plan summary for an agent."""
    stmt = select(AgentPlan).where(
        and_(
            AgentPlan.user_id == user_id,
            AgentPlan.agent_type == agent_type,
        )
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.plan_summary = plan_summary
        existing.created_at = datetime.utcnow()
    else:
        db.add(AgentPlan(
            user_id=user_id,
            agent_type=agent_type,
            plan_summary=plan_summary,
        ))
    await db.flush()


async def get_other_agent_plan(
    db: AsyncSession, user_id: uuid.UUID, current_agent: str
) -> str | None:
    """Get the latest plan from the OTHER agent for cross-agent coordination."""
    other = "dietologist" if current_agent == "trainer" else "trainer"
    stmt = select(AgentPlan).where(
        and_(
            AgentPlan.user_id == user_id,
            AgentPlan.agent_type == other,
        )
    )
    result = await db.execute(stmt)
    plan = result.scalar_one_or_none()
    return plan.plan_summary if plan else None
