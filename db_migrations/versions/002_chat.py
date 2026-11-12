"""Create the chat schema and its application role."""

from alembic import op

revision = "002_chat"
down_revision = "001_knowledge_base"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF current_database() <> 'psb_knowledge'
               OR to_regclass('knowledge.documents') IS NULL
               OR to_regclass('knowledge.document_versions') IS NULL
               OR to_regclass('knowledge.document_chunks') IS NULL
               OR to_regtype('public.vector') IS NULL THEN
                RAISE EXCEPTION 'Initialize psb_knowledge with migrations/001_knowledge.sql first';
            END IF;
        END
        $$;
    """)
    op.execute("CREATE SCHEMA chat")
    op.execute("REVOKE ALL ON SCHEMA chat FROM PUBLIC")
    op.execute("CREATE ROLE psb_chat_backend NOLOGIN INHERIT")
    op.execute("GRANT psb_knowledge_reader TO psb_chat_backend")
    op.execute("GRANT USAGE ON SCHEMA chat TO psb_chat_backend")

    op.execute("""
        CREATE TABLE chat.anonymous_users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            created_at timestamptz NOT NULL DEFAULT now(),
            last_seen_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE chat.chats (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL REFERENCES chat.anonymous_users (id) ON DELETE CASCADE,
            title text NOT NULL DEFAULT 'Новый чат' CHECK (title ~ '[^[:space:]]'),
            is_title_custom boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX chats_owner_updated_idx ON chat.chats (owner_id, updated_at DESC)
    """)
    op.execute("""
        CREATE TABLE chat.messages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            chat_id uuid NOT NULL REFERENCES chat.chats (id) ON DELETE CASCADE,
            reply_to_message_id uuid,
            role text NOT NULL CHECK (role IN ('user', 'assistant')),
            content text NOT NULL DEFAULT '',
            status text CHECK (status IN ('pending', 'completed', 'failed')),
            error_code text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT message_role_status_chk CHECK (
                (
                    role = 'user' AND status IS NULL AND reply_to_message_id IS NULL
                    AND content ~ '[^[:space:]]'
                )
                OR (
                    role = 'assistant' AND status IS NOT NULL
                    AND (status <> 'completed' OR content ~ '[^[:space:]]')
                )
            ),
            CONSTRAINT messages_error_status_chk CHECK (
                error_code IS NULL OR status IS NOT DISTINCT FROM 'failed'
            ),
            CONSTRAINT messages_chat_id_id_unique UNIQUE (chat_id, id),
            CONSTRAINT messages_reply_same_chat_fk
                FOREIGN KEY (chat_id, reply_to_message_id)
                REFERENCES chat.messages (chat_id, id)
                ON DELETE SET NULL (reply_to_message_id)
        )
    """)
    op.execute("""
        CREATE INDEX messages_chat_chronology_idx ON chat.messages (chat_id, created_at, id)
    """)
    op.execute("""
        CREATE INDEX messages_reply_idx ON chat.messages (reply_to_message_id)
        WHERE reply_to_message_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX messages_one_answer_per_question_idx
        ON chat.messages (reply_to_message_id)
        WHERE role = 'assistant' AND reply_to_message_id IS NOT NULL
    """)
    op.execute("""
        CREATE TABLE chat.chat_memory (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            chat_id uuid NOT NULL REFERENCES chat.chats (id) ON DELETE CASCADE,
            source_message_id uuid,
            memory_type text NOT NULL CHECK (memory_type IN ('context', 'summary')),
            content text NOT NULL CHECK (content ~ '[^[:space:]]'),
            embedding public.vector(1024) CHECK (public.vector_norm(embedding) > 0),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT chat_memory_source_same_chat_fk
                FOREIGN KEY (chat_id, source_message_id)
                REFERENCES chat.messages (chat_id, id)
                ON DELETE SET NULL (source_message_id)
        )
    """)
    op.execute("CREATE INDEX chat_memory_chat_id_idx ON chat.chat_memory (chat_id)")
    op.execute("""
        CREATE INDEX chat_memory_source_idx ON chat.chat_memory (source_message_id)
        WHERE source_message_id IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX chat_memory_fts_ru_idx ON chat.chat_memory
        USING gin (to_tsvector('pg_catalog.russian'::regconfig, content))
    """)
    op.execute("""
        GRANT SELECT, INSERT, UPDATE, DELETE
        ON chat.anonymous_users, chat.chats, chat.messages, chat.chat_memory
        TO psb_chat_backend
    """)


def downgrade() -> None:
    op.execute("DROP TABLE chat.chat_memory")
    op.execute("DROP TABLE chat.messages")
    op.execute("DROP TABLE chat.chats")
    op.execute("DROP TABLE chat.anonymous_users")
    op.execute("DROP SCHEMA chat")
    op.execute("REVOKE psb_knowledge_reader FROM psb_chat_backend")
    op.execute("DROP ROLE psb_chat_backend")
