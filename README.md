# Hackathon

Project scaffold for a juridical assistant.

- `app/`: API, configuration, database, services, LLM and RAG modules.
- `knowledge_base/`: source documents for retrieval.
- `scripts/`: knowledge base ingestion scripts.
- `migrations/`: database migrations.
- `tests/`: test placeholders.
- `frontend/`: frontend placeholder.

Files are scaffolding only; application logic and infrastructure configuration are not implemented yet.

Local configuration belongs in `.env` (excluded from Git). Use `.env.example` as the configuration template once variables are defined.

Add the source PDF at `knowledge_base/source_documents/psb_rules.pdf` before implementing ingestion.
