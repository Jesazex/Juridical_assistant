"""Chat HTTP contract. Foreign and absent chats are 404."""
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response

from app.api.dependencies import AnonId, DBSession
from app.schemas.chat import ChatCreate, ChatListQuery, ChatListResponse, ChatResponse, ChatUpdate
from app.services import chat_service

router = APIRouter(responses={404: {"description": "Chat not found or owned by another user"}})


@asynccontextmanager
async def chat_transaction(db):
    try:
        async with db.begin():
            yield
    except chat_service.ChatNotFound:
        raise HTTPException(status_code=404, detail="Chat not found") from None


@router.post("/", response_model=ChatResponse, status_code=201)
async def create_chat(payload: ChatCreate, db: DBSession, owner_id: AnonId):
    async with chat_transaction(db):
        chat = await chat_service.create_chat(db, owner_id, payload.title)
        result = ChatResponse.model_validate(chat)
    return result


@router.get("/", response_model=ChatListResponse)
async def list_chats(query: Annotated[ChatListQuery, Query()], db: DBSession, owner_id: AnonId):
    result = await chat_service.list_chats(db, owner_id, query.limit, query.offset)
    return ChatListResponse.model_validate(result)


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(chat_id: int, db: DBSession, owner_id: AnonId):
    async with chat_transaction(db):
        chat = await chat_service.get_chat(db, owner_id, chat_id)
        result = ChatResponse.model_validate(chat)
    return result


@router.patch("/{chat_id}", response_model=ChatResponse)
async def rename_chat(chat_id: int, payload: ChatUpdate, db: DBSession, owner_id: AnonId):
    async with chat_transaction(db):
        chat = await chat_service.rename_chat(db, owner_id, chat_id, payload.title)
        result = ChatResponse.model_validate(chat)
    return result


@router.delete("/{chat_id}", status_code=204, response_class=Response)
async def delete_chat(chat_id: int, db: DBSession, owner_id: AnonId):
    async with chat_transaction(db):
        await chat_service.delete_chat(db, owner_id, chat_id)
    return Response(status_code=204)
