# PSB · юридический ассистент

Юридический ассистент хранит нормативные документы в схеме `knowledge`, а историю и память пользователей — в схеме `chat` одной базы PostgreSQL 17 с pgvector. Внешний ключ связывает цитату с фрагментом документа. Память чата используется для уточнения контекста вопроса, а юридические источники берутся из применимых редакций документов.

Настройка ниже относится к веб-прототипу. Автоматическая проверка хакатона отдельно запускает `solution.py` с `questions.csv` и `knowledge-base.zip` из `DATA_DIR`. Автоматический сабмит на этом этапе ещё не реализован.

## Запуск сайта

Понадобится Docker с Compose v2. Если `.env` ещё нет, скопируйте `.env.example` и задайте пароль в `PSB_KNOWLEDGE_ADMIN_PASSWORD`. Для уже созданного тома используйте его действующий пароль.

```powershell
docker compose up -d --build --wait
```

Откройте `http://127.0.0.1:8080`. Nginx направляет `/api/v1/` на FastAPI, а отдельный сервис `migrate` применяет Alembic до старта API. По умолчанию порты сайта и базы доступны только с этого компьютера. Для запуска с отдельной прикладной учётной записью укажите `PSB_CONTAINER_DATABASE_URL` с адресом `knowledge-db:5432`. В локальной конфигурации без этого параметра API использует учётную запись администратора. При HTTPS включите `PSB_COOKIE_SECURE=true`.

Пока сервис генерации не подключён, отправленный вопрос сохраняется, а ответ получает статус `failed` с кодом `generation_unavailable`. Повторная попытка использует существующий ответ. Каталог показывает документы, загруженные в PostgreSQL.

## Корпус и поиск

```powershell
docker compose run --rm migrate python -m scripts.ingest_knowledge_base
```

Импорт загружает TXT из `knowledge_base/source_documents` и сохраняет редакции и пункты. Повторный запуск проверяет контрольные суммы и не дублирует записи. Для расчёта отсутствующих векторов задайте `LLM_BASE_URL` и `LLM_API_KEY` в локальном `.env`, затем выполните `python -m scripts.ingest_knowledge_base --embed` из PyCharm. Без векторов доступен текстовый поиск. Страницы не присваиваются фрагментам из TXT.

## Запуск Python из PyCharm

Выберите Python 3.12 или 3.13, интерпретатор `.venv` и корень проекта как рабочую папку. Укажите `PSB_DATABASE_URL` в формате `postgresql+asyncpg://psb_knowledge_admin:<URL-encoded-password>@127.0.0.1:5433/psb_knowledge`. Используйте порт из `PSB_KNOWLEDGE_PORT`.

```powershell
python -m pip install -r requirements.txt
docker compose up -d --wait knowledge-db
python -m alembic upgrade head
python -m alembic current
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

На пустом томе Docker выполняет `migrations/001_knowledge.sql`. Alembic проверяет наличие этой структуры, фиксирует baseline и добавляет таблицы чатов и цитат. На существующем томе с готовой схемой `knowledge` достаточно `python -m alembic upgrade head`. Для отдельной пустой базы, созданной вручную, сначала примените исходный SQL от администратора.

```powershell
Get-Content -Raw -Encoding utf8 migrations/001_knowledge.sql | docker compose exec -T knowledge-db psql -v ON_ERROR_STOP=1 -U psb_knowledge_admin -d psb_knowledge
```

## Проверка

```powershell
Get-Content -Raw -Encoding utf8 scripts/check_knowledge_db.sql | docker compose exec -T knowledge-db psql -v ON_ERROR_STOP=1 -U psb_knowledge_admin -d psb_knowledge
python -m scripts.check_python_db
python -m pytest -q
```

В Windows PowerShell 5.1 перед передачей SQL через конвейер установите `$OutputEncoding = [System.Text.UTF8Encoding]::new($false)`, чтобы сохранить русский текст. SQL и Python создают тестовые записи в транзакции и затем откатывают её. Python проверяет восемь таблиц, каскадное удаление, доступ к истории, повторную генерацию и поиск памяти.

## Данные и доступ

- `knowledge.documents` хранит название, тип, номер при наличии, ссылку на файл в корпусе и метаданные.
- `knowledge.document_versions` хранит редакции с SHA-256 содержимого. Период действия начинается в `effective_from` включительно и заканчивается перед `effective_to`. `NULL` в дате начала означает, что дата неизвестна. `NULL` в дате окончания может означать открытый период или отсутствие данных о его конце. Историческую применимость нужно подтверждать источником. Если редакции для одной даты пересекаются, выбор и учёт допсоглашений остаются задачей обработки корпуса.
- `knowledge.document_chunks` хранит порядок фрагмента, путь к разделу, текст, страницы при наличии и вектор из 1024 компонент. Пока вектор не вычислен, поле `embedding` может быть `NULL`. Для будущего импорта планируется BAAI/bge-m3 из кейса. Для текста есть GIN-индекс с русской конфигурацией, для векторов — HNSW с косинусной дистанцией.

- `chat.anonymous_users`, `chat.chats`, `chat.messages` и `chat.chat_memory` хранят пользователей, их чаты, сообщения и контекст. Запросы к репозиториям ограничены владельцем и чатом.
- `chat.answer_citations` хранит UUID фрагмента и снимок источника. Удаление чата каскадно удаляет его сообщения, память и цитаты. Документы остаются в `knowledge`.

Для миграций и локальной проверки используется `psb_knowledge_admin`. Отдельным прикладным ролям с `LOGIN` можно выдать членство в `psb_knowledge_reader` для чтения документов или в `psb_chat_backend` для работы с чатами и чтения документов. Второй backend отвечает за анонимную cookie, передачу проверенного `owner_id` и транзакции.

Сохраняйте сообщение пользователя и резервируйте `pending`-ответ до вызова модели. У новой попытки `started_at` передаётся в `complete_answer` или `fail_answer`, чтобы поздний ответ старого запроса не перезаписал новую попытку. Репозиторий создаёт снимки из найденных UUID фрагментов после того, как backend проверит, что они подтверждают ответ.

Клиент BAAI/bge-m3 читает `LLM_BASE_URL`, `LLM_API_KEY` и при необходимости `EMB_MODEL` из окружения или `.env`. Поиск памяти объединяет косинусный и русскоязычный полнотекстовый поиск в пределах одного чата. `app.rag.knowledge.retriever.search_knowledge` ищет фрагменты документов с фильтрами номера, даты и типа. Проверка того, что выбранные фрагменты подтверждают ответ, относится к сервису генерации.

## Структура командного проекта

- `app/`: модули API, БД, RAG и интеграции с моделями.
- `knowledge_base/`: исходные документы корпуса.
- `scripts/`: проверка базы и каркас загрузки корпуса.
- `migrations/`: исходный SQL для нового тома.
- `db_migrations/`: история миграций Alembic.
- `tests/`: тесты Python.
- `frontend/`: каркас интерфейса.
