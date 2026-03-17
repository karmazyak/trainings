"""add user fields, document chunk metadata, and full-text search

Revision ID: 003
Revises: 002
Create Date: 2026-03-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── User: new fields ──
    op.add_column("users", sa.Column("limitations", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("allergies", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("activity_level", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("gender", sa.String(20), nullable=True))

    # ── DocumentChunk: metadata fields ──
    op.add_column("document_chunks", sa.Column("chapter", sa.String(500), nullable=True))
    op.add_column("document_chunks", sa.Column("context_prefix", sa.Text(), nullable=True))
    op.add_column("document_chunks", sa.Column("domain", sa.String(50), nullable=True))
    op.add_column("document_chunks", sa.Column("topic_tags", ARRAY(sa.String()), nullable=True))
    op.add_column("document_chunks", sa.Column("token_count", sa.Integer(), nullable=True))

    # ── DocumentChunk: full-text search ──
    op.add_column("document_chunks", sa.Column("search_vector", TSVECTOR(), nullable=True))
    op.create_index(
        "ix_document_chunks_search_vector",
        "document_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_document_chunks_domain",
        "document_chunks",
        ["domain"],
    )

    # Populate search_vector for existing chunks
    op.execute(
        "UPDATE document_chunks SET search_vector = to_tsvector('russian', content) "
        "WHERE search_vector IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_domain")
    op.drop_index("ix_document_chunks_search_vector")
    op.drop_column("document_chunks", "search_vector")
    op.drop_column("document_chunks", "token_count")
    op.drop_column("document_chunks", "topic_tags")
    op.drop_column("document_chunks", "domain")
    op.drop_column("document_chunks", "context_prefix")
    op.drop_column("document_chunks", "chapter")
    op.drop_column("users", "gender")
    op.drop_column("users", "date_of_birth")
    op.drop_column("users", "activity_level")
    op.drop_column("users", "allergies")
    op.drop_column("users", "limitations")
