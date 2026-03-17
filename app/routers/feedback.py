import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Feedback, Message, UserPreference
from app.schemas import FeedbackCreate, FeedbackResponse, UserPreferenceResponse
from app.services.preferences import extract_preferences, save_preferences

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(data: FeedbackCreate, db: AsyncSession = Depends(get_db)):
    # Validate message exists
    msg = await db.get(Message, data.message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    feedback = Feedback(
        user_id=data.user_id,
        message_id=data.message_id,
        conversation_id=msg.conversation_id,
        agent_type=msg.conversation.agent_type if msg.conversation else "auto",
        rating=data.rating,
        comment=data.comment,
    )
    db.add(feedback)
    await db.flush()

    # Extract preferences from feedback comment (if any)
    if data.comment:
        prefs = await extract_preferences(
            text=data.comment,
            context=msg.content[:500],
        )
        if prefs:
            await save_preferences(db, data.user_id, prefs)

    # For negative feedback without comment, extract from the agent's response
    if data.rating == 1 and not data.comment:
        prefs = await extract_preferences(
            text="Пользователю НЕ понравился этот ответ",
            context=msg.content[:500],
        )
        if prefs:
            await save_preferences(db, data.user_id, prefs)

    await db.commit()
    return FeedbackResponse(id=feedback.id)


@router.get("/preferences/{user_id}", response_model=list[UserPreferenceResponse])
async def get_preferences(user_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(UserPreference)
        .where(UserPreference.user_id == user_id)
        .order_by(UserPreference.confidence.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
