from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import DBSession, OwnerId, chat_transaction
from app.db.repositories.message_repository import PendingAnswer
from app.schemas.message import (
    MessageCreate, MessageExchangeResponse, MessageListQuery, MessageListResponse, MessageResponse,
)
from app.services import message_service

router = APIRouter()


@asynccontextmanager
async def message_transaction(db: AsyncSession) -> AsyncIterator[None]:
    try:
        async with chat_transaction(db):
            yield
    except message_service.MessageNotFound as exc:
        raise HTTPException(status_code=404, detail="Message not found") from exc
    except message_service.MessageNotRetryable as exc:
        raise HTTPException(status_code=409, detail="Message cannot be retried") from exc


def schedule_answer(
    background_tasks: BackgroundTasks, request: Request, owner_id: UUID,
    chat_id: UUID, pending: PendingAnswer,
) -> None:
    if pending.started_at is not None:
        background_tasks.add_task(
            message_service.process_pending_answer, request.app.state.session_factory,
            owner_id, chat_id, pending.message.id, pending.started_at,
        )


@router.get("/", response_model=MessageListResponse)
async def list_messages(
    chat_id: UUID, query: Annotated[MessageListQuery, Query()], db: DBSession, owner_id: OwnerId,
) -> MessageListResponse:
    async with message_transaction(db):
        items, total = await message_service.list_messages(
            db, owner_id, chat_id, query.limit, query.offset,
        )
        response = MessageListResponse(
            items=items, total=total, limit=query.limit, offset=query.offset,
        )
    return response


@router.post("/", response_model=MessageExchangeResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    chat_id: UUID, body: MessageCreate, request: Request, background_tasks: BackgroundTasks,
    db: DBSession, owner_id: OwnerId,
) -> MessageExchangeResponse:
    async with message_transaction(db):
        question, pending = await message_service.send_message(db, owner_id, chat_id, body.content)
        response = MessageExchangeResponse(
            user_message=MessageResponse.from_message(question),
            assistant_message=MessageResponse.from_message(pending.message),
        )
    schedule_answer(background_tasks, request, owner_id, chat_id, pending)
    return response


@router.post("/{message_id}/retry", response_model=MessageResponse)
async def retry_message(
    chat_id: UUID, message_id: UUID, request: Request, background_tasks: BackgroundTasks,
    db: DBSession, owner_id: OwnerId,
) -> MessageResponse:
    async with message_transaction(db):
        pending = await message_service.retry_message(db, owner_id, chat_id, message_id)
        response = MessageResponse.from_message(pending.message)
    schedule_answer(background_tasks, request, owner_id, chat_id, pending)
    return response
