from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import DBSession, OwnerId, chat_transaction
from app.schemas.chat import ChatCreate, ChatListQuery, ChatListResponse, ChatResponse, ChatUpdate
from app.services import chat_service

router = APIRouter()


@router.post("/", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(body: ChatCreate, db: DBSession, owner_id: OwnerId) -> ChatResponse:
    async with chat_transaction(db):
        chat = await chat_service.create_chat(db, owner_id, body.title)
        response = ChatResponse.model_validate(chat)
    return response


@router.get("/", response_model=ChatListResponse)
async def list_chats(
    query: Annotated[ChatListQuery, Query()], db: DBSession, owner_id: OwnerId
) -> ChatListResponse:
    async with chat_transaction(db):
        items, total = await chat_service.list_chats(db, owner_id, query.limit, query.offset)
        response = ChatListResponse(
            items=[ChatResponse.model_validate(chat) for chat in items],
            total=total, limit=query.limit, offset=query.offset,
        )
    return response


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(chat_id: UUID, db: DBSession, owner_id: OwnerId) -> ChatResponse:
    async with chat_transaction(db):
        chat = await chat_service.get_chat(db, owner_id, chat_id)
        response = ChatResponse.model_validate(chat)
    return response


@router.patch("/{chat_id}", response_model=ChatResponse)
async def rename_chat(
    chat_id: UUID, body: ChatUpdate, db: DBSession, owner_id: OwnerId
) -> ChatResponse:
    async with chat_transaction(db):
        chat = await chat_service.rename_chat(db, owner_id, chat_id, body.title)
        response = ChatResponse.model_validate(chat)
    return response


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: UUID, db: DBSession, owner_id: OwnerId) -> Response:
    async with chat_transaction(db):
        await chat_service.delete_chat(db, owner_id, chat_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
