# PSB · юридический ассистент

Юридический ассистент хранит нормативные документы в схеме `knowledge`, а историю и память пользователей — в схеме `chat` одной базы PostgreSQL 17 с pgvector. Внешний ключ связывает цитату с фрагментом документа. Память чата используется для уточнения контекста вопроса, а юридические источники берутся из применимых редакций документов.

Настройка ниже относится к веб-прототипу. Автоматическая проверка хакатона отдельно запускает `solution.py` с `questions.csv` и `knowledge-base.zip` из `DATA_DIR`. Автоматический сабмит на этом этапе ещё не реализован.

## Запуск сайта

Понадобится Docker с Compose v2. Если `.env` ещё нет, скопируйте `.env.example` и задайте пароль в `PSB_KNOWLEDGE_ADMIN_PASSWORD`. Для уже созданного тома используйте его действующий пароль.

```powershell
docker compose up -d --build --wait
```

Откройте `http://127.0.0.1:8080`. Nginx направляет `/api/v1/` на FastAPI, а отдельный сервис `migrate` применяет Alembic до старта API. По умолчанию порты сайта и базы доступны только с этого компьютера. Для запуска с отдельной прикладной учётной записью укажите `PSB_CONTAINER_DATABASE_URL` с адресом `knowledge-db:5432`. В локальной конфигурации без этого параметра API использует учётную запись администратора. При HTTPS включите `PSB_COOKIE_SECURE=true`.

### Origin, cookies и HTTPS

В браузере API всегда доступен по относительному `/api/v1` на том же origin,
что и сайт. Nginx сохраняет исходный `Host` вместе с портом. Anonymous cookie
имеет `HttpOnly`, `SameSite=Lax`, `Path=/` и передаётся с `credentials: include`.
Не смешивайте `localhost` и `127.0.0.1` в одной сессии: cookies привязаны к хосту.

Локальные настройки `.env`:

```dotenv
PSB_PUBLIC_SCHEME=http
PSB_COOKIE_SECURE=false
PSB_CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173
PSB_DEV_API_UPSTREAM=http://127.0.0.1:8000
```

Если `PSB_CORS_ORIGINS` не задан или пуст, используются перечисленные четыре
локальных origin. Непустое значение **заменяет** список; несколько origin
разделяются запятыми. Same-origin запросы разрешены также на других портах.
Проверка Origin и запрет межсайтовых запросов без Origin сохраняются.

Для Vite запустите PostgreSQL через Compose, backend из корня проекта командой
`python -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000`,
а из `frontend/` — `npm ci` и `npm run dev`. Dev/preview-прокси читает
`PSB_DEV_API_UPSTREAM` из общего `.env` и сохраняет Host браузера.
Контейнерный API наружу не опубликован; Vite по умолчанию обращается к backend,
запущенному на хосте.

Для production завершайте TLS на внешнем reverse proxy на том же сервере.
Он направляет сайт и `/api/` на `http://127.0.0.1:8080`, сохраняет исходный Host
и перенаправляет внешний HTTP на HTTPS. Пример location внутри существующего
HTTPS server с настроенным сертификатом:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

В `.env` на сервере задайте свой домен:

```dotenv
PSB_PUBLIC_SCHEME=https
PSB_COOKIE_SECURE=true
PSB_CORS_ORIGINS=https://example.com
```

`PSB_PUBLIC_SCHEME` — внешняя схема (`http` или `https`). Внутренний frontend
Nginx выставляет её из окружения, **не доверяя** полученному от клиента
`X-Forwarded-Proto`; это сохраняет HTTPS после TLS termination. Uvicorn доверяет
forwarded-заголовкам только от фиксированного IP frontend Nginx. Сам FastAPI
не интерпретирует произвольные forwarded-заголовки.

По умолчанию выделенная сеть API/frontend — `172.30.80.0/24`, IP Nginx —
`172.30.80.2`. Динамический пул `PSB_WEB_DYNAMIC_RANGE=172.30.80.128/25`
не включает статический IP Nginx. При конфликте сети измените `PSB_WEB_SUBNET`,
`PSB_WEB_DYNAMIC_RANGE` и `PSB_FRONTEND_PROXY_IP` в `.env`, сохранив это разделение;
Compose использует последний и как адрес Nginx,
и как `FORWARDED_ALLOW_IPS` для Uvicorn. Не заменяйте его на `*`.
Порты API остаются внутренними, а frontend опубликован на loopback для внешнего
reverse proxy. Исходный код и frontend-сборка от домена не зависят.

При первом переходе со старой сети пересоздайте Compose-сеть; том PostgreSQL
сохраняется:

```powershell
docker compose down
docker compose up -d --build --wait
```

После последующих изменений `.env` достаточно второй команды, чтобы применить
окружение к пересозданным контейнерам.

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

## Интеграционные тесты Chat API

Тесты используют PostgreSQL 17 с pgvector из существующего сервиса `knowledge-db`
в `compose.yaml`. Отдельный контейнер или установленный в Windows PostgreSQL не нужен.
После установки и запуска Docker Desktop выполните из корня проекта:

```powershell
# Предварительно задайте PSB_KNOWLEDGE_ADMIN_PASSWORD в .env.
docker compose up -d --wait knowledge-db
# Выполнить один раз: создаёт отдельную пустую БД в существующем контейнере.
docker compose exec -T knowledge-db createdb -U psb_knowledge_admin psb_knowledge_test
```

Если база `psb_knowledge_test` уже существует, повторять `createdb` не требуется.
В `.env` или в переменных окружения PyCharm задайте:

```dotenv
TEST_DATABASE_URL=postgresql+asyncpg://psb_knowledge_admin:<URL-encoded-password>@127.0.0.1:5433/psb_knowledge_test
```

Используйте пароль из `PSB_KNOWLEDGE_ADMIN_PASSWORD` и порт из `PSB_KNOWLEDGE_PORT`.
`PSB_DATABASE_URL` оставьте адресом рабочей базы, не подменяйте его тестовым.
Затем запустите тесты в настроенном окружении проекта:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rs
```

При отсутствии `TEST_DATABASE_URL` интеграционные сценарии пропускаются с объяснением,
остальные тесты выполняются. Некорректный URL или недоступная настроенная тестовая БД
считаются ошибкой, а не причиной скрытого пропуска тестов.

До подключения проверяются драйвер `postgresql+asyncpg`, суффикс имени БД `_test`
и отличие от имени рабочей базы. В тестовой базе автоматически создаются расширение
`vector`, схемы `knowledge`, `chat` и таблицы из текущих SQLAlchemy-моделей.
Это проверка API и моделей, не проверка истории миграций: существующий baseline
Alembic привязан к имени `psb_knowledge`. Применять рабочий bootstrap SQL или менять
миграции для этих тестов не требуется.

Каждый сценарий использует внешнюю транзакцию и savepoints, данные откатываются
после теста. Тесты не выполняют `DROP`, `TRUNCATE` и не очищают рабочую базу.
DeepSeek и RAG не вызываются. Полный прогон PostgreSQL-сценариев требует запущенного Docker.

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
