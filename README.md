# PSB · база знаний

Первый этап юридического ассистента. Миграция создаёт реестр документов, их редакции и фрагменты в PostgreSQL 17 с расширением pgvector. Дерево Python повторяет `startup_dirs.TXT`. Импорт корпуса, вычисление эмбеддингов и API поиска относятся к следующим этапам.

Настройка ниже относится к веб-прототипу. Автоматическая проверка хакатона отдельно запускает `solution.py` с `questions.csv` и `knowledge-base.zip` из `DATA_DIR`. Автоматический сабмит на этом этапе ещё не реализован.

## Локальный запуск

Понадобится Docker с Compose v2. Скопируйте `.env.example` в `.env` и задайте собственный пароль в `PSB_KNOWLEDGE_ADMIN_PASSWORD`. PostgreSQL доступен на `127.0.0.1:5433`. Порт можно изменить в `PSB_KNOWLEDGE_PORT`.

```powershell
docker compose up -d --wait knowledge-db
```

Docker выполняет миграцию при первом запуске на пустом томе. Для существующей пустой базы `psb_knowledge`, где миграция ещё не применялась, запустите её один раз от администратора.

```powershell
Get-Content -Raw -Encoding utf8 migrations/001_knowledge.sql | docker compose exec -T knowledge-db psql -v ON_ERROR_STOP=1 -U psb_knowledge_admin -d psb_knowledge
```

## Проверка

```powershell
Get-Content -Raw -Encoding utf8 scripts/check_knowledge_db.sql | docker compose exec -T knowledge-db psql -v ON_ERROR_STOP=1 -U psb_knowledge_admin -d psb_knowledge
```

В Windows PowerShell 5.1 перед передачей SQL через конвейер установите `$OutputEncoding = [System.Text.UTF8Encoding]::new($false)`, чтобы сохранить русский текст. Проверка создаёт тестовые данные внутри транзакции и откатывает их после проверок связей, даты, размерности вектора, поиска и прав. Она также проверяет, что посторонняя роль не может подключиться к базе.

## Данные и доступ

- `knowledge.documents` хранит название, тип, номер при наличии, ссылку на файл в корпусе и метаданные.
- `knowledge.document_versions` хранит редакции с SHA-256 содержимого. Период действия начинается в `effective_from` включительно и заканчивается перед `effective_to`. `NULL` в дате начала означает, что дата неизвестна. `NULL` в дате окончания может означать открытый период или отсутствие данных о его конце. Историческую применимость нужно подтверждать источником. Если редакции для одной даты пересекаются, выбор и учёт допсоглашений остаются задачей обработки корпуса.
- `knowledge.document_chunks` хранит порядок фрагмента, путь к разделу, текст, страницы при наличии и вектор из 1024 компонент. Пока вектор не вычислен, поле `embedding` может быть `NULL`. Для будущего импорта планируется BAAI/bge-m3 из кейса. Для текста есть GIN-индекс с русской конфигурацией, для векторов — HNSW с косинусной дистанцией.

Документы работают на отдельном экземпляре PostgreSQL со своим томом и сетью Compose. Доступ `PUBLIC` к базе отозван. Для backend выдайте отдельной роли с `LOGIN` членство в `psb_knowledge_reader`. Эта роль читает только три таблицы документов. Учётная запись `psb_knowledge_admin` предназначена для настройки базы. Будущему сервису чатов потребуется собственное подключение к отдельному экземпляру. Источник для ответа можно будет сохранять на стороне чатов по UUID фрагмента и снимку цитаты.

## Структура командного проекта

- `app/`: API, configuration, database, services, LLM and RAG modules.
- `knowledge_base/`: source documents for retrieval.
- `scripts/`: knowledge base ingestion scripts.
- `migrations/`: database migrations.
- `tests/`: test placeholders.
- `frontend/`: frontend placeholder.
