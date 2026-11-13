from hashlib import sha256
from re import fullmatch
from secrets import token_urlsafe

ANONYMOUS_COOKIE = "anon_id"
ANONYMOUS_COOKIE_MAX_AGE = 30 * 24 * 60 * 60


def anonymous_token(cookie_value: str | None) -> tuple[str, bool]:
    if cookie_value is not None and fullmatch(r"[A-Za-z0-9_-]{43}", cookie_value):
        return cookie_value, False
    return token_urlsafe(32), True


def token_hash(token: str) -> str:
    return sha256(token.encode("ascii")).hexdigest()
