from uuid import UUID
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import BaseRequest


class MessageCreate(BaseRequest):
    """Отправка нового пользовательского сообщения: только его текст.

    Роль user, владелец, статус генерации, источники RAG, идентификаторы
    и временные метки определяются backend и запрещены во входном теле.
    Эта схема не разрешает редактирование уже отправленных сообщений.
    Согласованный лимит 10 000 символов ограничивает объём входного текста
    согласно требованию §5.3; он проверяется после удаления пробелов по краям.
    """

    content: str = Field(min_length=1, max_length=10_000)

    @field_validator("content", mode="before")
    @classmethod
    def validate_content(cls, value):
        # strip() удаляет пробельные символы по краям, сохраняя форматирование
        # внутри текста. До min_length и max_length нормализуем ввод, чтобы
        # пустой вопрос отклонялся, а внешние пробелы не занимали лимит длины.
        if isinstance(value, str):
            value = value.strip()
        return value


class MessageListQuery(BaseRequest):
    """Параметры страницы истории конкретного чата.

    Клиент задаёт только размер страницы и смещение. Проверку принадлежности
    чата и хронологическую сортировку выполняет соответствующий слой backend,
    поэтому полей владельца и порядка сортировки здесь нет.
    Подключать через Annotated[MessageListQuery, Query()]: пагинация истории
    передаётся в URL GET-запроса, а не в Request Body.
    """

    # По умолчанию выдаём 50 сообщений. ge=1 и le=100 задают допустимый
    # размер страницы; offset=0 начинает историю с начала, ge=0 исключает минус.
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class MessageSource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: int | str | None = None
    document_title: str | None = None
    chunk_id: int | str | None = None
    page: int | None = None
    excerpt: str | None = None
    url: str | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_id: UUID
    role: Literal["user", "assistant"]
    content: str
    status: Literal["pending", "completed", "failed"]
    sources: list[MessageSource]
    created_at: datetime
    updated_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int
    limit: int
    offset: int


class MessageExchangeResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
