"""Add feedback, user_preferences, agent_plans tables.

Revision ID: 004
Revises: 003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("agent_type", sa.String(20), nullable=False),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "user_preferences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("source", sa.String(20), server_default="feedback"),
        sa.Column("confidence", sa.Float, server_default="0.5"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_user_preferences_user_category", "user_preferences", ["user_id", "category"])

    op.create_table(
        "agent_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agent_type", sa.String(20), nullable=False),
        sa.Column("plan_summary", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_plans_user_agent", "agent_plans", ["user_id", "agent_type"])


def downgrade() -> None:
    op.drop_index("ix_agent_plans_user_agent")
    op.drop_table("agent_plans")
    op.drop_index("ix_user_preferences_user_category")
    op.drop_table("user_preferences")
    op.drop_table("feedback")
