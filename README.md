# Hackathon

Project scaffold for a juridical assistant.

- `app/`: API, configuration, database, services, LLM and RAG modules.
- `knowledge_base/`: source documents for retrieval.
- `scripts/`: knowledge base ingestion scripts.
- `migrations/`: database migrations.
- `tests/`: test placeholders.
- `frontend/`: веб-интерфейс чата для юриста — история диалогов, ответ и фрагменты базы, на которые он опирается.

Backend-модули в `app/` остаются каркасом: логика RAG и эндпоинты сообщений подключаются отдельно. Интерфейс уже говорит с контрактом `/api/v1`.

## Frontend

Нужны Node.js 22 и запущенный API на `http://127.0.0.1:8000`.

```bash
cd frontend
npm ci
npm run dev
```

Интерфейс открывается на [http://127.0.0.1:5173](http://127.0.0.1:5173). Запросы к `/api` проксируются на порт 8000, cookie `anon_id` остаётся HttpOnly и в код страницы не попадает.

Проверить вёрстку без модели и без API:

```bash
cd frontend
npm ci
npm run dev:mock
```

Сборка статики и контейнер:

```bash
cd frontend && npm ci && npm run build
docker compose up --build frontend
```

Контейнер слушает порт **8080**. `docker-compose.yml` задаёт `API_UPSTREAM=http://host.docker.internal:8000`, чтобы страница ходила в API на хосте. В самом образе запасной адрес — `http://api:8000`.

Клиент отправляет только разрешённые поля: `{ "content" }` для сообщения и `{ "title" }` для переименования. Список чатов и история читаются страницами `limit` / `offset`. Источники ответа ожидаются в `sources`: документ, фрагмент, страница, цитата и ссылка — только если их вернул сервер.

Local configuration belongs in `.env` (excluded from Git). Use `.env.example` as the configuration template once variables are defined.

Add the source PDF at `knowledge_base/source_documents/psb_rules.pdf` before implementing ingestion.
