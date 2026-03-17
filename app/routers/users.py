import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CachedPlan, User
from app.schemas import UserCreate, UserResponse, UserUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])

# Fields that affect plan generation — changing them invalidates cache
PLAN_RELEVANT_FIELDS = {
    "goal", "fitness_level", "training_style", "activity_level",
    "height_cm", "weight_kg", "limitations", "dietary_restrictions", "allergies",
}


@router.post("", response_model=UserResponse)
async def create_user(data: UserCreate, db: AsyncSession = Depends(get_db)):
    user = User(**data.model_dump())
    db.add(user)
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
        if deleted:
            logger.info("Invalidated %d cached plans for user %s (changed: %s)",
                        deleted, user_id, list(changed_fields.keys()))

    await db.commit()
    await db.refresh(user)
    return user
