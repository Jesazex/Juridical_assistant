from fastapi import APIRouter

from app.api.v1.endpoints import chats, health, messages

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(chats.router, prefix="/chats", tags=["Chats"])
api_router.include_router(messages.router, prefix="/chats/{chat_id}/messages", tags=["Messages"])
