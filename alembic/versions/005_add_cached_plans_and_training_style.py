"""Add cached_plans table and training_style field to users.

Revision ID: 005
Revises: 004
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add training_style to users
    op.add_column("users", sa.Column("training_style", sa.String(50), nullable=True))

    # Create cached_plans table
    op.create_table(
        "cached_plans",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_type", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.JSON(), nullable=True),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_cached_plans_user_type_week",
        "cached_plans",
        ["user_id", "plan_type", "week_number", "year"],
    )


def downgrade() -> None:
    op.drop_index("ix_cached_plans_user_type_week", "cached_plans")
    op.drop_table("cached_plans")
    op.drop_column("users", "training_style")
