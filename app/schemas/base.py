from pydantic import BaseModel, ConfigDict


class BaseRequest(BaseModel):
    """Общий контракт входящих данных API.

    extra="forbid" отклоняет неизвестные поля вместо их молчаливого удаления:
    frontend не должен подменять внутренние атрибуты, назначаемые backend.
    Все Request-схемы наследуют этот запрет.
    """

    model_config = ConfigDict(extra="forbid")
