"""Initial schema: sessions, app_settings, kb_documents, kb_chunks

Revision ID: 0001
Revises:
Create Date: 2026-11-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # sessions
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'")),
    )

    # app_settings
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(256), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # kb_documents
    op.create_table(
        "kb_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("file_path", sa.Text(), nullable=False, unique=True),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="ok"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # kb_chunks
    op.create_table(
        "kb_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("kb_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("content_tsv", TSVECTOR(), nullable=True),
    )

    # Generated tsvector trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION kb_chunks_tsv_update() RETURNS trigger AS $$
        BEGIN
            NEW.content_tsv := to_tsvector('english', COALESCE(NEW.content, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER kb_chunks_tsv_trigger
        BEFORE INSERT OR UPDATE OF content ON kb_chunks
        FOR EACH ROW EXECUTE FUNCTION kb_chunks_tsv_update();
    """)

    # Indexes
    op.create_index("ix_kb_chunks_gin", "kb_chunks", ["content_tsv"], postgresql_using="gin")
    op.execute("""
        CREATE INDEX ix_kb_chunks_hnsw ON kb_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_hnsw")
    op.drop_index("ix_kb_chunks_gin", table_name="kb_chunks")
    op.execute("DROP TRIGGER IF EXISTS kb_chunks_tsv_trigger ON kb_chunks")
    op.execute("DROP FUNCTION IF EXISTS kb_chunks_tsv_update()")
    op.drop_table("kb_chunks")
    op.drop_table("kb_documents")
    op.drop_table("app_settings")
    op.drop_table("sessions")
