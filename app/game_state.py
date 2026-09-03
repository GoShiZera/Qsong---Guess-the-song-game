import json
import time
import uuid
from typing import Any, cast

from itsdangerous import TimestampSigner

from app.config import settings
from app.models import GameState

_signer = TimestampSigner(settings.session_secret)

# In-memory session store with TTL (for Render free tier)
_session_store: dict[str, tuple[GameState, float]] = {}
_SESSION_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def serialize_session(data: dict[str, Any]) -> str:
    return _signer.sign(json.dumps(data).encode()).decode()


def deserialize_session(cookie: str) -> dict[str, Any] | None:
    try:
        unsigned = _signer.unsign(cookie.encode(), max_age=60 * 60 * 24 * 7).decode()
        return cast(dict[str, Any], json.loads(unsigned))
    except Exception:
        return None


def _cleanup_expired_sessions() -> None:
    """Remove expired sessions from the store."""
    current_time = time.time()
    expired_keys = [
        session_id
        for session_id, (_, timestamp) in _session_store.items()
        if current_time - timestamp > _SESSION_TTL_SECONDS
    ]
    for key in expired_keys:
        del _session_store[key]


def create_game_session(state: GameState) -> str:
    """Create a new game session and return session ID."""
    _cleanup_expired_sessions()
    session_id = uuid.uuid4().hex
    _session_store[session_id] = (state, time.time())
    return session_id


def get_game_session(session_id: str) -> GameState | None:
    _cleanup_expired_sessions()
    entry = _session_store.get(session_id)
    if entry is None:
        return None
    return entry[0]


def update_game_session(session_id: str, state: GameState) -> bool:
    _cleanup_expired_sessions()
    if session_id in _session_store:
        _session_store[session_id] = (state, time.time())
        return True
    return False


def delete_game_session(session_id: str) -> bool:
    _cleanup_expired_sessions()
    if session_id in _session_store:
        del _session_store[session_id]
        return True
    return False


def serialize_session_data(data: dict[str, Any]) -> str:
    return serialize_session(data)


def deserialize_session_data(cookie: str) -> dict[str, Any] | None:
    return deserialize_session(cookie)