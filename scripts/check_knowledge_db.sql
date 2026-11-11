BEGIN;

DO $$
DECLARE
    test_document_id uuid;
    test_edition_id uuid;
    test_chunk_id uuid;
    query_embedding public.vector(1024) :=
        ('[1' || repeat(',0', 1023) || ']')::public.vector;
BEGIN
    INSERT INTO knowledge.documents (title, document_type, source_file)
    VALUES ('Тестовый договор', 'Договор', 'fixture.pdf')
    RETURNING id INTO test_document_id;

    INSERT INTO knowledge.document_versions (document_id, version_label, effective_from, content_hash)
    VALUES (test_document_id, 'Тестовая редакция', DATE '2026-01-01', repeat('a', 64))
    RETURNING id INTO test_edition_id;

    INSERT INTO knowledge.document_chunks (
        version_id, chunk_index, section_path, page_from, content, embedding
    )
    VALUES (test_edition_id, 0, '§ 1. Согласование', 3, 'Порядок согласования договора', query_embedding)
    RETURNING id INTO test_chunk_id;

    PERFORM 1
    FROM knowledge.document_chunks AS c
    JOIN knowledge.document_versions AS v ON v.id = c.version_id
    JOIN knowledge.documents AS d ON d.id = v.document_id
    WHERE c.id = test_chunk_id
      AND d.id = test_document_id
      AND c.page_from = 3
      AND v.effective_from <= DATE '2026-02-01'
      AND (v.effective_to IS NULL OR v.effective_to > DATE '2026-02-01')
      AND to_tsvector('pg_catalog.russian'::regconfig, c.content)
          @@ plainto_tsquery('pg_catalog.russian'::regconfig, 'договор')
      AND (c.embedding OPERATOR(public.<=>) query_embedding) < 0.000001;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Could not find the test fragment by text and vector';
    END IF;

    BEGIN
        INSERT INTO knowledge.document_chunks (version_id, chunk_index, content)
        VALUES (test_edition_id, 0, 'Дубликат фрагмента');
        RAISE EXCEPTION 'Duplicate chunk position was accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO knowledge.document_chunks (version_id, chunk_index, content)
        VALUES (gen_random_uuid(), 0, 'Фрагмент без редакции');
        RAISE EXCEPTION 'Chunk without a parent edition was accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO knowledge.document_versions (
            document_id, version_label, effective_from, effective_to, content_hash
        )
        VALUES (test_document_id, 'Тестовый период', DATE '2026-02-01', DATE '2026-01-01', repeat('b', 64));
        RAISE EXCEPTION 'Invalid edition dates were accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO knowledge.document_chunks (version_id, chunk_index, content, embedding)
        VALUES (test_edition_id, 1, 'Вектор другой размерности', '[1,2]');
        RAISE EXCEPTION 'Embedding with the wrong dimensions was accepted';
    EXCEPTION WHEN data_exception THEN NULL;
    END;
END;
$$;

CREATE ROLE psb_knowledge_check_unrelated NOLOGIN;

DO $$
BEGIN
    IF has_database_privilege('psb_knowledge_check_unrelated', current_database(), 'CONNECT')
       OR has_schema_privilege('psb_knowledge_check_unrelated', 'knowledge', 'USAGE')
       OR has_table_privilege('psb_knowledge_check_unrelated', 'knowledge.documents', 'SELECT') THEN
        RAISE EXCEPTION 'An unrelated role has access to the document database';
    END IF;
END;
$$;

SET LOCAL ROLE psb_knowledge_reader;

DO $$
BEGIN
    IF NOT has_database_privilege(current_database(), 'CONNECT') THEN
        RAISE EXCEPTION 'The reader cannot connect to the document database';
    END IF;

    PERFORM id FROM knowledge.documents;
    PERFORM id FROM knowledge.document_versions;
    PERFORM id FROM knowledge.document_chunks;

    BEGIN
        INSERT INTO knowledge.documents (title, document_type, source_file)
        VALUES ('Запись от читателя', 'Тест', 'test.pdf');
        RAISE EXCEPTION 'The reader has write access';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;

    IF has_schema_privilege('knowledge', 'CREATE')
       OR has_schema_privilege('public', 'CREATE')
       OR has_database_privilege(current_database(), 'CREATE') THEN
        RAISE EXCEPTION 'The reader can create database objects';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('r', 'p')
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND (n.nspname, c.relname) NOT IN (
              ('knowledge', 'documents'),
              ('knowledge', 'document_versions'),
              ('knowledge', 'document_chunks')
          )
    ) THEN
        RAISE EXCEPTION 'Unexpected application tables in the document database';
    END IF;
END;
$$;

ROLLBACK;
