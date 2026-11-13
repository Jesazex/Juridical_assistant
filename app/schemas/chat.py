from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.schemas.base import BaseRequest


class ChatCreate(BaseRequest):
    title: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", when_used="json")
    def serialize_utc(self, value: datetime) -> str:
        """Preserve the existing timezone-less Chat JSON contract."""
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat()


class ChatListResponse(BaseModel):
    items: list[ChatResponse]
    total: int
    limit: int
    offset: int


class ChatUpdate(BaseRequest):
    """Переименование чата: клиент передаёт только новое название.

    id, owner_id и временные метки не входят в тело запроса. Backend
    определяет текущего анонимного пользователя и проверяет владельца чата.
    Дополнительные поля запрещены базовым классом.
    Лимит 100 символов сохраняет название компактным для списка чатов.
    """

    title: str = Field(min_length=1, max_length=100)

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, value):
        # strip() выполняется до обеих проверок длины; min_length затем
        # отклоняет и пустую строку, и название только из пробельных символов.
        if isinstance(value, str):
            value = value.strip()
        return value


class ChatListQuery(BaseRequest):
    """Параметры страницы списка чатов текущего анонимного пользователя.

    Клиент управляет только размером страницы и смещением, а не owner_id.
    Фильтрацию по владельцу и сортировку по активности выполняет backend.
    Подключать через Annotated[ChatListQuery, Query()]: это параметры GET URL,
    а не тело запроса, чтобы страницу можно было задать обычной ссылкой.
    """

    # По умолчанию выдаём 20 чатов. ge=1 исключает пустые страницы,
    # le=100 ограничивает объём одной выборки, ge=0 запрещает смещение назад.
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
