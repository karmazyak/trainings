from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AgentType(str, Enum):
    trainer = "trainer"
    dietologist = "dietologist"
    auto = "auto"  # auto-detect via router agent


# ── Users ──────────────────────────────────────────────


class _UserFieldValidators:
    """Shared validators for UserCreate and UserUpdate."""

    @field_validator("height_cm")
    @classmethod
    def validate_height(cls, v: float | None) -> float | None:
        if v is not None and not 50 <= v <= 300:
            raise ValueError("height_cm must be between 50 and 300")
        return v

    @field_validator("weight_kg")
    @classmethod
    def validate_weight(cls, v: float | None) -> float | None:
        if v is not None and not 10 <= v <= 500:
            raise ValueError("weight_kg must be between 10 and 500")
        return v

    @field_validator("test_pushups")
    @classmethod
    def validate_pushups(cls, v: int | None) -> int | None:
        if v is not None and not 0 <= v <= 500:
            raise ValueError("test_pushups must be between 0 and 500")
        return v

    @field_validator("test_plank_sec")
    @classmethod
    def validate_plank(cls, v: int | None) -> int | None:
        if v is not None and not 0 <= v <= 3600:
            raise ValueError("test_plank_sec must be between 0 and 3600")
        return v

    @field_validator("test_squats")
    @classmethod
    def validate_squats(cls, v: int | None) -> int | None:
        if v is not None and not 0 <= v <= 500:
            raise ValueError("test_squats must be between 0 and 500")
        return v

    @field_validator("preferred_training_days")
    @classmethod
    def validate_training_days(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                days = [int(d.strip()) for d in v.split(",") if d.strip()]
                if not all(1 <= d <= 7 for d in days):
                    raise ValueError
            except ValueError:
                raise ValueError("preferred_training_days must be comma-separated integers 1-7")
        return v

    @field_validator("training_style")
    @classmethod
    def validate_training_style(cls, v: str | None) -> str | None:
        allowed = ("gym", "home", "crossfit", "running", "run", "yoga", "sport", "rest")
        if v is not None and v not in allowed:
            raise ValueError(f"training_style must be one of: {', '.join(allowed)}")
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        allowed = ("male", "female")
        if v is not None and v not in allowed:
            raise ValueError(f"gender must be one of: {', '.join(allowed)}")
        return v


class WeekScheduleSlotCreate(BaseModel):
    day_of_week: int  # 1-7
    activity_type: str  # gym, home, run, yoga, sport, rest
    sport_name: str | None = None

    @field_validator("day_of_week")
    @classmethod
    def validate_day(cls, v: int) -> int:
        if not 1 <= v <= 7:
            raise ValueError("day_of_week must be 1-7")
        return v

    @field_validator("activity_type")
    @classmethod
    def validate_activity(cls, v: str) -> str:
        allowed = ("gym", "home", "run", "yoga", "sport", "rest")
        if v not in allowed:
            raise ValueError(f"activity_type must be one of: {', '.join(allowed)}")
        return v


class UserCreate(_UserFieldValidators, BaseModel):
    name: str = Field(max_length=100)
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    goal: str | None = Field(None, max_length=200)
    fitness_level: str | None = Field(None, max_length=50)
    training_style: str | None = Field(None, max_length=50)
    limitations: str | None = Field(None, max_length=1000)
    dietary_restrictions: str | None = Field(None, max_length=500)
    allergies: str | None = Field(None, max_length=500)
    activity_level: str | None = Field(None, max_length=100)
    date_of_birth: date | None = None
    gender: str | None = Field(None, max_length=20)
    preferred_training_days: str | None = Field(None, max_length=50)
    test_pushups: int | None = None
    test_plank_sec: int | None = None
    test_squats: int | None = None
    fitness_test_date: date | None = None
    schedule_template: str | None = None  # "gym3", "gym_run", "home3", "yoga_run"
    week_schedule: list[WeekScheduleSlotCreate] | None = None


class UserUpdate(_UserFieldValidators, BaseModel):
    name: str | None = Field(None, max_length=100)
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    goal: str | None = Field(None, max_length=200)
    fitness_level: str | None = Field(None, max_length=50)
    training_style: str | None = Field(None, max_length=50)
    limitations: str | None = Field(None, max_length=1000)
    dietary_restrictions: str | None = Field(None, max_length=500)
    allergies: str | None = Field(None, max_length=500)
    activity_level: str | None = Field(None, max_length=100)
    date_of_birth: date | None = None
    gender: str | None = Field(None, max_length=20)
    preferred_training_days: str | None = Field(None, max_length=50)
    test_pushups: int | None = None
    test_plank_sec: int | None = None
    test_squats: int | None = None
    fitness_test_date: date | None = None


class UserResponse(BaseModel):
    id: UUID
    name: str
    age: int | None
    height_cm: float | None
    weight_kg: float | None
    goal: str | None
    fitness_level: str | None
    training_style: str | None
    limitations: str | None
    dietary_restrictions: str | None
    allergies: str | None
    activity_level: str | None
    date_of_birth: date | None
    gender: str | None
    preferred_training_days: str | None
    test_pushups: int | None
    test_plank_sec: int | None
    test_squats: int | None
    fitness_test_date: date | None
    current_streak: int = 0
    max_streak: int = 0
    last_training_date: date | None = None

    model_config = {"from_attributes": True}


# ── Chat ───────────────────────────────────────────────


class SourceReference(BaseModel):
    book: str
    chapter: str | None = None
    relevance: float | None = None


class ChatRequest(BaseModel):
    user_id: UUID
    agent: AgentType = AgentType.auto
    message: str
    conversation_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message cannot be empty")
        if len(v) > 4000:
            raise ValueError("message cannot exceed 4000 characters")
        return v


class ChatResponse(BaseModel):
    conversation_id: UUID
    agent_used: str  # "trainer", "dietologist", "both"
    message: str
    message_db_id: UUID | None = None
    sources: list[SourceReference] = []


# ── Feedback ─────────────────────────────────────────


class FeedbackCreate(BaseModel):
    user_id: UUID
    message_id: UUID
    rating: int  # 1=thumbs down, 5=thumbs up
    comment: str | None = Field(None, max_length=2000)

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int) -> int:
        if v not in (1, 5):
            raise ValueError("rating must be 1 (thumbs down) or 5 (thumbs up)")
        return v


class FeedbackResponse(BaseModel):
    id: UUID
    status: str = "ok"


class UserPreferenceResponse(BaseModel):
    category: str
    key: str
    value: str
    confidence: float

    model_config = {"from_attributes": True}


# ── Documents ──────────────────────────────────────────


class DocumentUploadResponse(BaseModel):
    document_name: str
    chunks_count: int


class DocumentStatsResponse(BaseModel):
    total_chunks: int
    by_domain: dict[str, int]
    by_source: dict[str, int]


class IngestFolderResponse(BaseModel):
    processed: list[DocumentUploadResponse]
    errors: list[str]


# ── Exercise ───────────────────────────────────────────


class ExerciseAnalyzeResponse(BaseModel):
    analysis_id: UUID
    exercise_name: str
    reps_count: int
    analysis_report: str
    trainer_feedback: str


# ── Plans (cached) ────────────────────────────────────


class PlanResponse(BaseModel):
    plan_type: str
    content: str
    sources: list[SourceReference] = []
    cached: bool = False  # True if served from cache
    week_number: int
    created_at: str | None = None


class MyDayResponse(BaseModel):
    workout: str | None = None
    meal: str | None = None
    day_label: str = ""  # e.g. "Понедельник"
    session_id: str | None = None  # training_session UUID for complete/skip
    session_status: str | None = None  # scheduled, completed, skipped
    session_type: str | None = None  # training, rest, cardio
    session_title: str | None = None
    activity_type: str | None = None  # gym, home, run, yoga, sport, rest
    current_streak: int = 0
    max_streak: int = 0
    exercise_progress: list[dict] | None = None  # [{exercise_name, exercise_label, previous_weight, suggested_weight}]


# ── Schedule (training sessions) ─────────────────────


class TrainingSessionResponse(BaseModel):
    id: UUID
    day_of_week: int
    session_type: str
    title: str | None
    workout_content: str | None
    meal_content: str | None
    status: str
    user_feedback: str | None
    difficulty_rating: int | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class WeekScheduleResponse(BaseModel):
    week_number: int
    year: int
    sessions: list[TrainingSessionResponse]
    stats: dict  # completed, skipped, scheduled counts


class CompleteSessionResponse(BaseModel):
    """Response after completing a session — includes streak info."""
    session: TrainingSessionResponse
    current_streak: int = 0
    max_streak: int = 0
    streak_just_broken: bool = False

    model_config = {"from_attributes": True}


class CompleteSessionRequest(BaseModel):
    feedback: str | None = Field(None, max_length=2000)
    difficulty_rating: int | None = None  # 1-5

    @field_validator("difficulty_rating")
    @classmethod
    def validate_difficulty(cls, v: int | None) -> int | None:
        if v is not None and not 1 <= v <= 5:
            raise ValueError("difficulty_rating must be between 1 and 5")
        return v


class SkipSessionRequest(BaseModel):
    reason: str | None = Field(None, max_length=1000)


# ── Week Schedule ─────────────────────────────────────


class WeekScheduleUpdate(BaseModel):
    """Full week schedule — 7 slots."""
    slots: list[WeekScheduleSlotCreate]


class WeekScheduleSlotResponse(BaseModel):
    day_of_week: int
    activity_type: str
    sport_name: str | None = None

    model_config = {"from_attributes": True}


# ── Exercise Log ──────────────────────────────────────


class ExerciseLogCreate(BaseModel):
    exercise_name: str  # normalized: "bench_press"
    exercise_label: str  # display: "Жим штанги лёжа"
    weight_kg: float
    reps: int
    sets: int
    rpe: float | None = None
    session_id: UUID | None = None


class ExerciseLogResponse(BaseModel):
    id: UUID
    exercise_name: str
    exercise_label: str
    weight_kg: float
    reps: int
    sets: int
    rpe: float | None
    logged_at: date

    model_config = {"from_attributes": True}


class ExerciseHistoryResponse(BaseModel):
    exercise_name: str
    exercise_label: str
    logs: list[ExerciseLogResponse]
    previous_weight: float | None = None
    suggested_weight: float | None = None


# ── Situation Chat ────────────────────────────────────


class SituationRequest(BaseModel):
    user_id: UUID
    situation: str  # "party", "shop", "delivery", "preworkout", "late_meal", or custom text
    subcategory: str | None = None  # "meat", "dairy", "snack" for shop
    conversation_id: UUID | None = None


class TryQuestionRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message cannot be empty")
        if len(v) > 4000:
            raise ValueError("message cannot exceed 4000 characters")
        return v


class TryQuestionResponse(BaseModel):
    message: str
    sources: list[SourceReference] = []
