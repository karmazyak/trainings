"""Add week_schedule_slots, exercise_logs, progress_goals tables + activity_type to training_sessions.

Revision ID: 012
Revises: 011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    # WeekScheduleSlot
    op.create_table(
        "week_schedule_slots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("activity_type", sa.String(20), nullable=False),
        sa.Column("sport_name", sa.String(100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_week_schedule_user_day",
        "week_schedule_slots",
        ["user_id", "day_of_week"],
        unique=True,
    )

    # ExerciseLog
    op.create_table(
        "exercise_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("exercise_name", sa.String(200), nullable=False),
        sa.Column("exercise_label", sa.String(200), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("rpe", sa.Float(), nullable=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("training_sessions.id"), nullable=True),
        sa.Column("logged_at", sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_exercise_logs_user_exercise", "exercise_logs", ["user_id", "exercise_name"])
    op.create_index("ix_exercise_logs_user_date", "exercise_logs", ["user_id", "logged_at"])

    # ProgressGoal
    op.create_table(
        "progress_goals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("exercise_name", sa.String(200), nullable=False),
        sa.Column("exercise_label", sa.String(200), nullable=False),
        sa.Column("target_weight_kg", sa.Float(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("current_weight_kg", sa.Float(), nullable=True),
        sa.Column("achieved", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_progress_goals_user", "progress_goals", ["user_id"])

    # TrainingSession — add activity_type column
    op.add_column("training_sessions", sa.Column("activity_type", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("training_sessions", "activity_type")
    op.drop_table("progress_goals")
    op.drop_table("exercise_logs")
    op.drop_table("week_schedule_slots")
