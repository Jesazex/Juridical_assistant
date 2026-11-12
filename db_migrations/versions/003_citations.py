"""Link verified answer citations to document chunks."""

from alembic import op

revision = "003_citations"
down_revision = "002_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE chat.answer_citations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id uuid NOT NULL REFERENCES chat.messages (id) ON DELETE CASCADE,
            chunk_id uuid REFERENCES knowledge.document_chunks (id) ON DELETE SET NULL,
            position integer NOT NULL CHECK (position >= 0),
            document_id_snapshot text,
            document_title_snapshot text NOT NULL CHECK (document_title_snapshot ~ '[^[:space:]]'),
            section_snapshot text,
            page_snapshot integer CHECK (page_snapshot > 0),
            excerpt_snapshot text,
            url_snapshot text,
            CONSTRAINT answer_citation_position_unique UNIQUE (message_id, position)
        )
    """)
    op.execute("""
        CREATE INDEX answer_citations_chunk_idx ON chat.answer_citations (chunk_id)
        WHERE chunk_id IS NOT NULL
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON chat.answer_citations TO psb_chat_backend")


def downgrade() -> None:
    op.execute("DROP TABLE chat.answer_citations")
