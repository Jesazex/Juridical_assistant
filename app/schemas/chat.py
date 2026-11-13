from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import BaseRequest, PaginatedResponse, PaginationQuery, validate_text


class ChatCreate(BaseRequest):
    title: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: object) -> object:
        return validate_text(value)


class ChatUpdate(BaseRequest):
    title: str = Field(min_length=1, max_length=100)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: object) -> object:
        return validate_text(value)


class ChatListQuery(PaginationQuery):
    pass


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatListResponse(PaginatedResponse[ChatResponse]):
    pass
