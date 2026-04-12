import logging
from collections import Counter
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ExerciseLog, ProgressGoal, User
from app.schemas import ExerciseLogCreate, ExerciseLogResponse, ExerciseHistoryResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/exercise-log", tags=["exercise-log"])

# Exercise name normalization
EXERCISE_MAP = {
    "жим штанги лёжа": "bench_press", "жим лёжа": "bench_press", "жим штанги лежа": "bench_press",
    "приседания": "squat", "присед": "squat", "приседания со штангой": "squat",
    "становая тяга": "deadlift", "становая": "deadlift",
    "жим стоя": "overhead_press", "жим штанги стоя": "overhead_press",
    "подтягивания": "pullups", "тяга верхнего блока": "lat_pulldown",
    "тяга штанги в наклоне": "barbell_row", "тяга в наклоне": "barbell_row",
    "выпады": "lunges", "жим гантелей": "dumbbell_press",
    "жим гантелей на наклонной": "incline_dumbbell_press",
    "разводка": "flyes", "разводка гантелей": "flyes",
    "сгибания на бицепс": "bicep_curl", "бицепс": "bicep_curl",
    "французский жим": "tricep_extension",
    "махи гантелями": "lateral_raise",
    "жим ногами": "leg_press",
}

LEG_EXERCISES = {"squat", "deadlift", "leg_press", "lunges", "bulgarian_split", "hip_thrust"}
ISOLATION_EXERCISES = {"bicep_curl", "tricep_extension", "lateral_raise", "face_pull", "flyes"}


def normalize_exercise_name(label: str) -> str:
    lower = label.lower().strip()
    if lower in EXERCISE_MAP:
        return EXERCISE_MAP[lower]
    # Fallback: simple transliteration + underscore
    import re
    name = re.sub(r'[^\w\s]', '', lower)
    name = re.sub(r'\s+', '_', name.strip())
    return name


def _progression_step(exercise_name: str) -> float:
    if exercise_name in LEG_EXERCISES:
        return 5.0
    if exercise_name in ISOLATION_EXERCISES:
        return 1.0
    return 2.5


@router.post("/{user_id}", response_model=ExerciseLogResponse)
async def create_exercise_log(user_id: UUID, data: ExerciseLogCreate, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    log = ExerciseLog(
        user_id=user.id,
        exercise_name=data.exercise_name,
        exercise_label=data.exercise_label,
        weight_kg=data.weight_kg,
        reps=data.reps,
        sets=data.sets,
        rpe=data.rpe,
        session_id=data.session_id,
        logged_at=date.today(),
    )
    db.add(log)

    # Update ProgressGoal if exists
    stmt = select(ProgressGoal).where(
        ProgressGoal.user_id == user.id,
        ProgressGoal.exercise_name == data.exercise_name,
        ProgressGoal.achieved == False,
    )
    result = await db.execute(stmt)
    goal = result.scalar_one_or_none()
    if goal:
        goal.current_weight_kg = data.weight_kg
        if data.weight_kg >= goal.target_weight_kg:
            goal.achieved = True

    await db.commit()
    await db.refresh(log)
    return log


@router.get("/{user_id}/history/{exercise_name}", response_model=ExerciseHistoryResponse)
async def get_exercise_history(
    user_id: UUID,
    exercise_name: str,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    stmt = (
        select(ExerciseLog)
        .where(ExerciseLog.user_id == user.id, ExerciseLog.exercise_name == exercise_name)
        .order_by(ExerciseLog.logged_at.desc(), ExerciseLog.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    logs = list(result.scalars().all())

    previous_weight = logs[0].weight_kg if logs else None
    label = logs[0].exercise_label if logs else exercise_name
    suggested = None
    if previous_weight is not None:
        suggested = previous_weight + _progression_step(exercise_name)

    return ExerciseHistoryResponse(
        exercise_name=exercise_name,
        exercise_label=label,
        logs=logs,
        previous_weight=previous_weight,
        suggested_weight=suggested,
    )


@router.get("/{user_id}/recent", response_model=list[ExerciseLogResponse])
async def get_recent_exercises(user_id: UUID, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    stmt = (
        select(ExerciseLog)
        .where(ExerciseLog.user_id == user.id)
        .order_by(ExerciseLog.logged_at.desc(), ExerciseLog.created_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{user_id}/session/{session_id}", response_model=list[ExerciseLogResponse])
async def get_session_exercises(user_id: UUID, session_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(ExerciseLog)
        .where(ExerciseLog.user_id == user_id, ExerciseLog.session_id == session_id)
        .order_by(ExerciseLog.created_at)
    )
    result = await db.execute(stmt)
    return result.scalars().all()
