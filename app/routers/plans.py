"""Plan caching router.

Stores generated plans per user/week to avoid re-generating every time.
Supports: workout_today, workout_week, meal_today, meal_week, full_plan.
"""

import json
import logging
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import llm_call_cheap
from app.agents.dietologist import dietologist_agent
from app.agents.router import handle_both, route_message
from app.agents.trainer import trainer_agent
from app.database import get_db
from app.models import CachedPlan, User
from app.rag.retriever import RetrievedChunk
from app.routers.chat import format_user_context, _build_sources
from app.schemas import MyDayResponse, PlanResponse, SourceReference
from app.services.preferences import (
    compress_plan,
    format_preferences_for_prompt,
    get_other_agent_plan,
    get_user_preferences,
    save_agent_plan,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plans", tags=["plans"])

# Map plan_type → (agent_key, prompt_template_name)
PLAN_AGENTS = {
    "workout_today": "trainer",
    "workout_week": "trainer",
    "meal_today": "dietologist",
    "meal_week": "dietologist",
    "full_plan": "auto",
}

DAY_NAMES_RU = {
    1: "Понедельник",
    2: "Вторник",
    3: "Среда",
    4: "Четверг",
    5: "Пятница",
    6: "Суббота",
    7: "Воскресенье",
}

EXTRACT_DAY_PROMPT = (
    "Из недельного плана ниже извлеки ТОЛЬКО информацию на {day_name} ({day_label}).\n"
    "Если день явно не указан — выбери наиболее подходящий по номеру дня.\n"
    "Ответь КРАТКО и КОМПАКТНО, без вступлений.\n\n"
    "План:\n{plan_text}\n"
)


def _current_week() -> tuple[int, int]:
    """Return (ISO week number, year)."""
    today = date.today()
    iso = today.isocalendar()
    return iso.week, iso.year


async def _get_cached(
    db: AsyncSession, user_id: UUID, plan_type: str
) -> CachedPlan | None:
    """Get cached plan for current week."""
    week, year = _current_week()
    stmt = select(CachedPlan).where(
        and_(
            CachedPlan.user_id == user_id,
            CachedPlan.plan_type == plan_type,
            CachedPlan.week_number == week,
            CachedPlan.year == year,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _generate_and_cache(
    db: AsyncSession,
    user: User,
    plan_type: str,
    prompt: str,
) -> tuple[str, list[SourceReference]]:
    """Generate plan via agents and cache it."""
    agent_key = PLAN_AGENTS[plan_type]

    prefs = await get_user_preferences(db, user.id)
    prefs_text = format_preferences_for_prompt(prefs)
    user_context = format_user_context(user)

    if agent_key == "auto":
        # Full plan uses both agents
        response_text, agent_used, chunks = await handle_both(
            user_message=prompt,
            db=db,
            history=[],
            user_context=user_context,
            preferences=prefs_text,
        )
    else:
        other_plan = await get_other_agent_plan(db, user.id, agent_key)
        agents = {"trainer": trainer_agent, "dietologist": dietologist_agent}
        agent = agents[agent_key]
        response_text, chunks = await agent.get_response(
            user_message=prompt,
            db=db,
            history=[],
            user_context=user_context,
            preferences=prefs_text,
            other_agent_plan=other_plan,
        )

    sources = _build_sources(chunks)
    sources_data = [s.model_dump() for s in sources]

    # Save to cache
    week, year = _current_week()

    # Remove old cache for this plan_type
    old = await _get_cached(db, user.id, plan_type)
    if old:
        await db.delete(old)
        await db.flush()

    cached = CachedPlan(
        user_id=user.id,
        plan_type=plan_type,
        content=response_text,
        sources_json=sources_data,
        week_number=week,
        year=year,
    )
    db.add(cached)

    # Also save compressed plan for cross-agent coordination
    if agent_key in ("trainer", "dietologist") and len(response_text) > 200:
        try:
            summary = await compress_plan(response_text, agent_key)
            if summary:
                await save_agent_plan(db, user.id, agent_key, summary)
        except Exception:
            logger.exception("Failed to save plan summary")

    await db.commit()
    return response_text, sources


@router.get("/{user_id}/{plan_type}", response_model=PlanResponse)
async def get_plan(
    user_id: UUID,
    plan_type: str,
    prompt: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Get plan from cache or generate new one.

    Query params:
    - prompt: the skill prompt to use for generation
    - force: if True, always regenerate
    """
    if plan_type not in PLAN_AGENTS:
        raise HTTPException(400, f"Unknown plan_type: {plan_type}")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    week, year = _current_week()

    # Check cache (unless force)
    if not force:
        cached = await _get_cached(db, user.id, plan_type)
        if cached:
            sources = []
            if cached.sources_json:
                sources = [SourceReference(**s) for s in cached.sources_json]
            return PlanResponse(
                plan_type=plan_type,
                content=cached.content,
                sources=sources,
                cached=True,
                week_number=week,
                created_at=cached.created_at.isoformat() if cached.created_at else None,
            )

    # Generate new
    content, sources = await _generate_and_cache(db, user, plan_type, prompt)
    return PlanResponse(
        plan_type=plan_type,
        content=content,
        sources=sources,
        cached=False,
        week_number=week,
    )


@router.get("/{user_id}/my-day", response_model=MyDayResponse)
async def get_my_day(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Extract today's workout + meal from cached weekly plans."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    today = date.today()
    iso_weekday = today.isoweekday()  # 1=Mon ... 7=Sun
    day_label = DAY_NAMES_RU.get(iso_weekday, "")
    day_number = f"День {iso_weekday}"

    workout_text = None
    meal_text = None

    # Try to get cached weekly plans
    workout_cache = await _get_cached(db, user.id, "workout_week")
    meal_cache = await _get_cached(db, user.id, "meal_week")

    # If no weekly plans, try today plans
    if not workout_cache:
        workout_cache = await _get_cached(db, user.id, "workout_today")
        if workout_cache:
            workout_text = workout_cache.content

    if not meal_cache:
        meal_cache = await _get_cached(db, user.id, "meal_today")
        if meal_cache:
            meal_text = meal_cache.content

    # Extract today's portion from weekly plans via cheap LLM
    if workout_cache and not workout_text:
        try:
            prompt = EXTRACT_DAY_PROMPT.format(
                day_name=day_number, day_label=day_label,
                plan_text=workout_cache.content[:3000],
            )
            workout_text = await llm_call_cheap(
                [{"role": "user", "content": prompt}], temperature=0.1
            )
        except Exception:
            logger.exception("Failed to extract today's workout")
            workout_text = None

    if meal_cache and not meal_text:
        try:
            prompt = EXTRACT_DAY_PROMPT.format(
                day_name=day_number, day_label=day_label,
                plan_text=meal_cache.content[:3000],
            )
            meal_text = await llm_call_cheap(
                [{"role": "user", "content": prompt}], temperature=0.1
            )
        except Exception:
            logger.exception("Failed to extract today's meal")
            meal_text = None

    return MyDayResponse(
        workout=workout_text,
        meal=meal_text,
        day_label=day_label,
    )
