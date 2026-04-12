import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CachedPlan, TrainingSession, User, WeekScheduleSlot
from app.schemas import (
    UserCreate, UserResponse, UserUpdate,
    WeekScheduleUpdate, WeekScheduleSlotResponse, WeekScheduleSlotCreate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])

SCHEDULE_TEMPLATES = {
    "gym3": {1: "gym", 2: "rest", 3: "gym", 4: "rest", 5: "gym", 6: "rest", 7: "rest"},
    "gym_run": {1: "gym", 2: "run", 3: "rest", 4: "gym", 5: "rest", 6: "rest", 7: "rest"},
    "home3": {1: "home", 2: "rest", 3: "home", 4: "rest", 5: "home", 6: "rest", 7: "rest"},
    "yoga_run": {1: "yoga", 2: "run", 3: "yoga", 4: "run", 5: "yoga", 6: "rest", 7: "rest"},
}


async def _create_schedule_slots(db: AsyncSession, user_id, template: str | None, slots_data: list | None):
    if template and template in SCHEDULE_TEMPLATES:
        tpl = SCHEDULE_TEMPLATES[template]
        for day, activity in tpl.items():
            db.add(WeekScheduleSlot(user_id=user_id, day_of_week=day, activity_type=activity))
    elif slots_data:
        for s in slots_data:
            db.add(WeekScheduleSlot(user_id=user_id, day_of_week=s.day_of_week, activity_type=s.activity_type, sport_name=s.sport_name))


# Fields that affect plan generation — changing them invalidates cache
PLAN_RELEVANT_FIELDS = {
    "goal", "fitness_level", "training_style", "activity_level",
    "height_cm", "weight_kg", "limitations", "dietary_restrictions", "allergies",
    "preferred_training_days",
    "test_pushups", "test_plank_sec", "test_squats",
}


@router.post("", response_model=UserResponse)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db)):
    user = User(**data.model_dump(exclude={"schedule_template", "week_schedule"}))
    db.add(user)
    await db.flush()

    if data.schedule_template or data.week_schedule:
        await _create_schedule_slots(db, user.id, data.schedule_template, data.week_schedule)
        # Compute backwards-compat fields
        slots = data.week_schedule or [
            WeekScheduleSlotCreate(day_of_week=d, activity_type=t)
            for d, t in SCHEDULE_TEMPLATES.get(data.schedule_template, {}).items()
        ]
        non_rest = [s for s in slots if s.activity_type != "rest"]
        if non_rest:
            from collections import Counter
            types = Counter(s.activity_type for s in non_rest)
            user.training_style = types.most_common(1)[0][0]
            user.preferred_training_days = ",".join(str(s.day_of_week) for s in non_rest)
            count = len(non_rest)
            if count <= 2:
                user.activity_level = "1-2 тренировки в неделю"
            elif count == 3:
                user.activity_level = "3 тренировки в неделю"
            elif count <= 5:
                user.activity_level = "4-5 тренировок в неделю"
            else:
                user.activity_level = "6-7 тренировок в неделю"

    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: UUID, data: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changed_fields = data.model_dump(exclude_unset=True)
    for field, value in changed_fields.items():
        setattr(user, field, value)

    # If any plan-relevant field changed → invalidate cached plans
    if changed_fields.keys() & PLAN_RELEVANT_FIELDS:
        result = await db.execute(
            delete(CachedPlan).where(CachedPlan.user_id == user.id)
        )
        deleted = result.rowcount
        # Only delete scheduled (future) sessions — keep completed/skipped for history
        result2 = await db.execute(
            delete(TrainingSession).where(
                TrainingSession.user_id == user.id,
                TrainingSession.status == "scheduled",
            )
        )
        deleted_sessions = result2.rowcount
        if deleted or deleted_sessions:
            logger.info("Invalidated %d cached plans + %d scheduled sessions for user %s (changed: %s)",
                        deleted, deleted_sessions, user_id, list(changed_fields.keys()))

    await db.commit()
    await db.refresh(user)
    return user


@router.put("/{user_id}/schedule", response_model=list[WeekScheduleSlotResponse])
async def update_schedule(user_id: UUID, data: WeekScheduleUpdate, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    # Delete old slots
    await db.execute(delete(WeekScheduleSlot).where(WeekScheduleSlot.user_id == user.id))

    # Insert new slots
    for s in data.slots:
        db.add(WeekScheduleSlot(user_id=user.id, day_of_week=s.day_of_week, activity_type=s.activity_type, sport_name=s.sport_name))

    # Update backwards-compat fields
    non_rest = [s for s in data.slots if s.activity_type != "rest"]
    if non_rest:
        from collections import Counter
        types = Counter(s.activity_type for s in non_rest)
        user.training_style = types.most_common(1)[0][0]
        user.preferred_training_days = ",".join(str(s.day_of_week) for s in non_rest)
        count = len(non_rest)
        if count <= 2:
            user.activity_level = "1-2 тренировки в неделю"
        elif count == 3:
            user.activity_level = "3 тренировки в неделю"
        elif count <= 5:
            user.activity_level = "4-5 тренировок в неделю"
        else:
            user.activity_level = "6-7 тренировок в неделю"

    # Invalidate cache
    await db.execute(delete(CachedPlan).where(CachedPlan.user_id == user.id))
    await db.execute(delete(TrainingSession).where(TrainingSession.user_id == user.id, TrainingSession.status == "scheduled"))

    await db.commit()

    # Return fresh slots
    result = await db.execute(select(WeekScheduleSlot).where(WeekScheduleSlot.user_id == user.id).order_by(WeekScheduleSlot.day_of_week))
    return result.scalars().all()


@router.get("/{user_id}/schedule", response_model=list[WeekScheduleSlotResponse])
async def get_schedule(user_id: UUID, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    result = await db.execute(select(WeekScheduleSlot).where(WeekScheduleSlot.user_id == user.id).order_by(WeekScheduleSlot.day_of_week))
    return result.scalars().all()
