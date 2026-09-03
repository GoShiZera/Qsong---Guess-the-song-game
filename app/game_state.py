import json
import uuid
from typing import Any, cast

from itsdangerous import TimestampSigner

from app.config import settings
from app.models import GameState

_signer = TimestampSigner(settings.session_secret)

# In-memory session store (for Render free tier)
_session_store: dict[str, GameState] = {}


def serialize_session(data: dict[str, Any]) -> str:
    return _signer.sign(json.dumps(data).encode()).decode()


def deserialize_session(cookie: str) -> dict[str, Any] | None:
    try:
        unsigned = _signer.unsign(cookie.encode(), max_age=60 * 60 * 24 * 7).decode()
        return cast(dict[str, Any], json.loads(unsigned))
    except Exception:
        return None


def create_game_session(state: GameState) -> str:
    """Create a new game session and return session ID."""
    session_id = uuid.uuid4().hex
    _session_store[session_id] = state
    return session_id


def get_game_session(session_id: str) -> GameState | None:
    return _session_store.get(session_id)


def update_game_session(session_id: str, state: GameState) -> bool:
    if session_id in _session_store:
        _session_store[session_id] = state
        return True
    return False


def delete_game_session(session_id: str) -> bool:
    if session_id in _session_store:
        del _session_store[session_id]
        return True
    return False


def serialize_session_data(data: dict[str, Any]) -> str:
    return serialize_session(data)


def deserialize_session_data(cookie: str) -> dict[str, Any] | None:
    return deserialize_session(cookie)