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

from app.agents.base import llm_call_cheap, LLMError
from app.agents.dietologist import dietologist_agent
from app.agents.router import handle_both, route_message
from app.agents.trainer import trainer_agent
from app.database import get_db
from app.models import CachedPlan, TrainingSession, User
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
    user_context = await format_user_context(user, db)

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

    # Auto-populate training schedule when workout_week is generated
    if plan_type in ("workout_week", "full_plan"):
        try:
            from app.routers.schedule import _parse_workout_week_into_sessions, _get_week_sessions

            existing = await _get_week_sessions(db, user.id, week, year)
            if existing:
                for s in existing:
                    await db.delete(s)
                await db.flush()

            meal_cache = await _get_cached(db, user.id, "meal_week") if plan_type == "workout_week" else None
            meal_plan = meal_cache.content if meal_cache else None

            # For full_plan, the response contains both workout and meal
            workout_text = response_text
            if plan_type == "full_plan":
                meal_plan = response_text  # full_plan has both, LLM will extract

            sessions = await _parse_workout_week_into_sessions(
                db, user, workout_text, meal_plan, week, year,
            )
            for s in sessions:
                db.add(s)
            await db.commit()
            logger.info("Auto-populated %d training sessions for user %s", len(sessions), user.id)
        except Exception:
            logger.exception("Failed to auto-populate training schedule")

    return response_text, sources


@router.get("/{user_id}/my-day", response_model=MyDayResponse)
async def get_my_day(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get today's workout + meal. Prefers training_sessions (instant), falls back to LLM extraction."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    today = date.today()
    iso_weekday = today.isoweekday()  # 1=Mon ... 7=Sun
    day_label = DAY_NAMES_RU.get(iso_weekday, "")

    # 1) Try training_sessions table first (instant, no LLM)
    week, year = _current_week()
    stmt = select(TrainingSession).where(
        and_(
            TrainingSession.user_id == user.id,
            TrainingSession.week_number == week,
            TrainingSession.year == year,
            TrainingSession.day_of_week == iso_weekday,
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session:
        return MyDayResponse(
            workout=session.workout_content,
            meal=session.meal_content,
            day_label=day_label,
            session_id=str(session.id),
            session_status=session.status,
            session_type=session.session_type,
            session_title=session.title,
            current_streak=user.current_streak,
            max_streak=user.max_streak,
        )

    # 2) Fallback: use cached weekly plans directly (no extra LLM call)
    workout_cache = await _get_cached(db, user.id, "workout_week")
    meal_cache = await _get_cached(db, user.id, "meal_week")

    if not workout_cache:
        workout_cache = await _get_cached(db, user.id, "workout_today")
    if not meal_cache:
        meal_cache = await _get_cached(db, user.id, "meal_today")

    workout_text = workout_cache.content if workout_cache else None
    meal_text = meal_cache.content if meal_cache else None

    return MyDayResponse(
        workout=workout_text,
        meal=meal_text,
        day_label=day_label,
        current_streak=user.current_streak,
        max_streak=user.max_streak,
    )


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
    try:
        content, sources = await _generate_and_cache(db, user, plan_type, prompt)
    except LLMError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return PlanResponse(
        plan_type=plan_type,
        content=content,
        sources=sources,
        cached=False,
        week_number=week,
    )
