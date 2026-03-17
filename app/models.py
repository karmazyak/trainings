import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, DateTime, Date, ForeignKey, Integer, Float, Enum as SAEnum, JSON, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    goal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fitness_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    training_style: Mapped[str | None] = mapped_column(String(50), nullable=True)  # gym, home, crossfit, running
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    dietary_restrictions: Mapped[str | None] = mapped_column(Text, nullable=True)
    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    activity_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    agent_type: Mapped[str] = mapped_column(String(20))  # "trainer" | "dietologist"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class ExerciseAnalysis(Base):
    __tablename__ = "exercise_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    exercise_name: Mapped[str] = mapped_column(String(200))
    video_filename: Mapped[str] = mapped_column(String(500))
    reps_count: Mapped[int] = mapped_column(Integer, default=0)
    analysis_report: Mapped[str] = mapped_column(Text)
    trainer_feedback: Mapped[str] = mapped_column(Text)
    keypoints_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship()


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"))
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    agent_type: Mapped[str] = mapped_column(String(20))
    rating: Mapped[int] = mapped_column(Integer)  # 1=thumbs down, 5=thumbs up
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    category: Mapped[str] = mapped_column(String(50))  # "training", "nutrition", "general"
    key: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="feedback")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_user_preferences_user_category", "user_id", "category"),
    )


class AgentPlan(Base):
    __tablename__ = "agent_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    agent_type: Mapped[str] = mapped_column(String(20))  # "trainer" or "dietologist"
    plan_summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_agent_plans_user_agent", "user_id", "agent_type"),
    )


class CachedPlan(Base):
    """Cached generated plans to avoid re-generating on every request."""
    __tablename__ = "cached_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    plan_type: Mapped[str] = mapped_column(String(30))  # workout_today, workout_week, meal_today, meal_week, full_plan
    content: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    week_number: Mapped[int] = mapped_column(Integer)  # ISO week number for cache invalidation
    year: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_cached_plans_user_type_week", "user_id", "plan_type", "week_number", "year"),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_name: Mapped[str] = mapped_column(String(500))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(384))
    # New fields for smart preprocessing
    chapter: Mapped[str | None] = mapped_column(String(500), nullable=True)
    context_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(50), nullable=True)
    topic_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Full-text search vector
    search_vector = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_document_chunks_domain", "domain"),
    )
