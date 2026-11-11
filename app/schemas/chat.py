from pydantic import Field, field_validator

from app.schemas.base import BaseRequest


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
