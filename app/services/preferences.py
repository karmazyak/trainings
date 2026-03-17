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
    """Format preferences list into text for agent system prompt."""
    if not prefs:
        return ""
    lines = []
    for p in prefs:
        conf = "высокая" if p["confidence"] >= 0.7 else "средняя"
        lines.append(f"- {p['value']} (уверенность: {conf})")
    return "\n".join(lines)


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
