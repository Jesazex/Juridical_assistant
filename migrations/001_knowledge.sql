BEGIN;

DO $$
BEGIN
    IF current_database() <> 'psb_knowledge' THEN
        RAISE EXCEPTION 'Apply the document migration to psb_knowledge only';
    END IF;
END;
$$;

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
CREATE SCHEMA knowledge;
CREATE ROLE psb_knowledge_reader NOLOGIN;

REVOKE ALL ON DATABASE psb_knowledge FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE psb_knowledge TO psb_knowledge_reader;
GRANT USAGE ON SCHEMA knowledge, public TO psb_knowledge_reader;

CREATE TABLE knowledge.documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL CHECK (title ~ '[^[:space:]]'),
    document_type text NOT NULL CHECK (document_type ~ '[^[:space:]]'),
    document_number text,
    source_file text NOT NULL CHECK (source_file ~ '[^[:space:]]'),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE knowledge.document_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES knowledge.documents (id) ON DELETE RESTRICT,
    version_label text NOT NULL CHECK (version_label ~ '[^[:space:]]'),
    effective_from date,
    effective_to date,
    source_file text CHECK (source_file ~ '[^[:space:]]'),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT document_versions_label_unique UNIQUE (document_id, version_label),
    CONSTRAINT document_versions_valid_period CHECK (
        effective_from IS NULL OR effective_to IS NULL OR effective_from < effective_to
    )
);

CREATE INDEX document_versions_document_date_idx
    ON knowledge.document_versions (document_id, effective_from DESC NULLS LAST);

CREATE TABLE knowledge.document_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id uuid NOT NULL REFERENCES knowledge.document_versions (id) ON DELETE RESTRICT,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    section_path text CHECK (section_path ~ '[^[:space:]]'),
    page_from integer CHECK (page_from > 0),
    page_to integer,
    content text NOT NULL CHECK (content ~ '[^[:space:]]'),
    embedding public.vector(1024) CHECK (public.vector_norm(embedding) > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT document_chunks_index_unique UNIQUE (version_id, chunk_index),
    CONSTRAINT document_chunks_valid_pages CHECK (
        page_to IS NULL OR (page_from IS NOT NULL AND page_to >= page_from)
    )
);

CREATE INDEX document_chunks_content_fts_idx
    ON knowledge.document_chunks
    USING gin (to_tsvector('pg_catalog.russian'::regconfig, content));

CREATE INDEX document_chunks_embedding_hnsw_idx
    ON knowledge.document_chunks USING hnsw (embedding public.vector_cosine_ops);

GRANT SELECT ON knowledge.documents, knowledge.document_versions, knowledge.document_chunks
    TO psb_knowledge_reader;

COMMIT;
