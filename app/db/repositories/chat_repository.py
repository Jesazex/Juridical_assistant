from re import fullmatch
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.anonymous_user import AnonymousUser
from app.db.models.chat import Chat


async def upsert_anonymous_user(session: AsyncSession, token_hash: str) -> AnonymousUser:
    """Resolve a verified token hash and record the visit in the caller's transaction."""
    if not fullmatch(r"[0-9a-f]{64}", token_hash):
        raise ValueError("token_hash must be a lowercase SHA-256 digest")
    statement = (
        insert(AnonymousUser)
        .values(token_hash=token_hash)
        .on_conflict_do_update(
            index_elements=[AnonymousUser.token_hash],
            set_={"last_seen_at": func.clock_timestamp()},
        )
        .returning(AnonymousUser)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(statement)).one()


async def create_chat(session: AsyncSession, owner_id: UUID) -> Chat:
    chat = Chat(owner_id=owner_id)
    session.add(chat)
    await session.flush()
    return chat


async def get_owned_chat(
    session: AsyncSession, chat_id: UUID, owner_id: UUID, *, for_update: bool = False
) -> Chat | None:
    statement = select(Chat).where(Chat.id == chat_id, Chat.owner_id == owner_id)
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(statement)


async def list_owned_chats(session: AsyncSession, owner_id: UUID) -> list[Chat]:
    result = await session.scalars(
        select(Chat)
        .where(Chat.owner_id == owner_id)
        .order_by(Chat.updated_at.desc(), Chat.id.desc())
    )
    return list(result)


async def rename_owned_chat(
    session: AsyncSession, chat_id: UUID, owner_id: UUID, title: str
) -> Chat | None:
    title = title.strip()
    if not title:
        raise ValueError("A chat title cannot be blank")
    return await session.scalar(
        update(Chat)
        .where(Chat.id == chat_id, Chat.owner_id == owner_id)
        .values(title=title, is_title_custom=True, updated_at=func.clock_timestamp())
        .returning(Chat)
        .execution_options(populate_existing=True)
    )


async def delete_owned_chat(session: AsyncSession, chat_id: UUID, owner_id: UUID) -> bool:
    deleted_id = await session.scalar(
        delete(Chat)
        .where(Chat.id == chat_id, Chat.owner_id == owner_id)
        .returning(Chat.id)
    )
    return deleted_id is not None
