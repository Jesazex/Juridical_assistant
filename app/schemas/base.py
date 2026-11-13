"""Shared request configuration and text normalization for API schemas."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


ItemT = TypeVar("ItemT")


class BaseRequest(BaseModel):
    """Reject unknown request fields to catch malformed client input."""

    model_config = ConfigDict(extra="forbid")


class PaginationQuery(BaseRequest):
    """Shared pagination bounds; concrete endpoints choose their default limit."""

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PaginatedResponse(BaseModel, Generic[ItemT]):
    """A page of items and its pagination metadata."""

    items: list[ItemT]
    total: int
    limit: int
    offset: int


def validate_text(value: object) -> object:
    """Trim strings, leaving nulls and type validation to the field schema."""
    return value.strip() if isinstance(value, str) else value
