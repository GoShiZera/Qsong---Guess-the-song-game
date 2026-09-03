import json
from typing import Any, cast

from itsdangerous import TimestampSigner

from app.config import settings
from app.models import GameState

_signer = TimestampSigner(settings.session_secret)


def serialize_session(data: dict[str, Any]) -> str:
    return _signer.sign(json.dumps(data).encode()).decode()


def deserialize_session(cookie: str) -> dict[str, Any] | None:
    try:
        unsigned = _signer.unsign(cookie.encode(), max_age=60 * 60 * 24 * 7).decode()
        return cast(dict[str, Any], json.loads(unsigned))
    except Exception:
        return None


def serialize_game_state(state: GameState) -> str:
    return serialize_session(state.model_dump(mode="json"))


def deserialize_game_state(cookie: str) -> GameState | None:
    data = deserialize_session(cookie)
    if data is None:
        return None
    try:
        return GameState.model_validate(data)
    except Exception:
        return None