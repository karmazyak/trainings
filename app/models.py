import uuid
from datetime import date, datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, String, Text, Date, ForeignKey, Integer, Float, Enum as SAEnum, JSON, Index, TIMESTAMP
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
    preferred_training_days: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "1,3,5" = Mon,Wed,Fri
    # Baseline fitness test
    test_pushups: Mapped[int | None] = mapped_column(Integer, nullable=True)  # max reps
    test_plank_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)  # seconds
    test_squats: Mapped[int | None] = mapped_column(Integer, nullable=True)  # max reps
    fitness_test_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Streak tracking
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    max_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_training_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")
    schedule_slots: Mapped[list["WeekScheduleSlot"]] = relationship(back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    agent_type: Mapped[str] = mapped_column(String(20))  # "trainer" | "dietologist"
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

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
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

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
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    category: Mapped[str] = mapped_column(String(50))  # "training", "nutrition", "general"
    key: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="feedback")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_user_preferences_user_category", "user_id", "category"),
    )


class AgentPlan(Base):
    __tablename__ = "agent_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    agent_type: Mapped[str] = mapped_column(String(20))  # "trainer" or "dietologist"
    plan_summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

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
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_cached_plans_user_type_week", "user_id", "plan_type", "week_number", "year"),
    )


class TrainingSession(Base):
    """One day in the user's weekly schedule — workout + meal + status."""
    __tablename__ = "training_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    week_number: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 1=Mon ... 7=Sun
    session_type: Mapped[str] = mapped_column(String(20), default="training")  # training, rest, cardio
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    workout_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    meal_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    activity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # gym, home, run, yoga, sport, rest
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled, completed, skipped
    user_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship()
    exercise_logs: Mapped[list["ExerciseLog"]] = relationship(back_populates="session")

    __table_args__ = (
        Index("ix_training_sessions_user_week", "user_id", "week_number", "year"),
        Index("ix_training_sessions_user_day", "user_id", "week_number", "year", "day_of_week", unique=True),
    )


class WeekScheduleSlot(Base):
    __tablename__ = "week_schedule_slots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    day_of_week: Mapped[int] = mapped_column(Integer)  # 1=Mon ... 7=Sun
    activity_type: Mapped[str] = mapped_column(String(20))  # gym, home, run, yoga, sport, rest
    sport_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="schedule_slots")

    __table_args__ = (
        Index("ix_week_schedule_user_day", "user_id", "day_of_week", unique=True),
    )


class ExerciseLog(Base):
    __tablename__ = "exercise_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    exercise_name: Mapped[str] = mapped_column(String(200))  # normalized: "bench_press"
    exercise_label: Mapped[str] = mapped_column(String(200))  # display: "Жим штанги лёжа"
    weight_kg: Mapped[float] = mapped_column(Float)
    reps: Mapped[int] = mapped_column(Integer)
    sets: Mapped[int] = mapped_column(Integer)
    rpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("training_sessions.id"), nullable=True)
    logged_at: Mapped[date] = mapped_column(Date, default=date.today)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship()
    session: Mapped["TrainingSession | None"] = relationship(back_populates="exercise_logs")

    __table_args__ = (
        Index("ix_exercise_logs_user_exercise", "user_id", "exercise_name"),
        Index("ix_exercise_logs_user_date", "user_id", "logged_at"),
    )


class ProgressGoal(Base):
    __tablename__ = "progress_goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    exercise_name: Mapped[str] = mapped_column(String(200))
    exercise_label: Mapped[str] = mapped_column(String(200))
    target_weight_kg: Mapped[float] = mapped_column(Float)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    achieved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship()

    __table_args__ = (
        Index("ix_progress_goals_user", "user_id"),
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
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_document_chunks_domain", "domain"),
    )
