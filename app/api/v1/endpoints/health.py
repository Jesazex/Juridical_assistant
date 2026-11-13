from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DBSession

router = APIRouter()


@router.get("/health")
async def health_check(db: DBSession) -> dict[str, str]:
    try:
        healthy = await db.scalar(text("SELECT 1")) == 1
    except (OSError, SQLAlchemyError):
        healthy = False
    if not healthy:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"status": "ok"}
