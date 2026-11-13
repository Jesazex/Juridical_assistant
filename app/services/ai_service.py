"""Mock AI boundary accepting JSON-compatible data.

Payload: {chat_id, message: {id, content}, history?: [{role, content}, ...]}.
History is optional; this module applies no history selection or truncation.
Result: {content, sources}. Raise an exception on generation failure.
"""


async def generate_reply(payload: dict) -> dict:
    return {"content": "Тестовый ответ AI", "sources": []}
