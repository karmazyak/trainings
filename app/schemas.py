from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class AgentType(str, Enum):
    trainer = "trainer"
    dietologist = "dietologist"
    auto = "auto"  # auto-detect via router agent


# ── Users ──────────────────────────────────────────────


class UserCreate(BaseModel):
    name: str
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    goal: str | None = None
    fitness_level: str | None = None
    training_style: str | None = None  # gym, home, crossfit, running
    limitations: str | None = None
    dietary_restrictions: str | None = None
    allergies: str | None = None
    activity_level: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    goal: str | None = None
    fitness_level: str | None = None
    training_style: str | None = None
    limitations: str | None = None
    dietary_restrictions: str | None = None
    allergies: str | None = None
    activity_level: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None


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
    comment: str | None = None


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
