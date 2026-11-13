"""Message API; clients can create only user messages."""
from uuid import UUID
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import AnonId, DBSession, chat_transaction
from app.schemas.message import MessageCreate, MessageListQuery, MessageListResponse, MessageExchangeResponse
from app.services import message_service, chat_service

router = APIRouter(responses={404: {"description": "Chat not found or owned by another user"}})


@router.post("/{chat_id}/messages", response_model=MessageExchangeResponse, status_code=201,
             response_model_exclude_none=True)
async def create_message(chat_id: UUID, payload: MessageCreate, db: DBSession, owner_id: AnonId):
    try:
        return await message_service.create_message(db, owner_id, chat_id, payload.content)
    except chat_service.ChatNotFound:
        raise HTTPException(status_code=404, detail="Chat not found") from None


@router.get("/{chat_id}/messages", response_model=MessageListResponse, response_model_exclude_none=True)
async def list_messages(chat_id: UUID, query: Annotated[MessageListQuery, Query()],
                        db: DBSession, owner_id: AnonId):
    async with chat_transaction(db):
        return await message_service.list_messages(db, owner_id, chat_id, query.limit, query.offset)
