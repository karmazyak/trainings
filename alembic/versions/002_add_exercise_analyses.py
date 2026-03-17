"""add exercise_analyses table

Revision ID: 002
Revises: 001
Create Date: 2026-03-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exercise_analyses",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("exercise_name", sa.String(200), nullable=False),
        sa.Column("video_filename", sa.String(500), nullable=False),
        sa.Column("reps_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analysis_report", sa.Text(), nullable=False),
        sa.Column("trainer_feedback", sa.Text(), nullable=False),
        sa.Column("keypoints_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("exercise_analyses")
