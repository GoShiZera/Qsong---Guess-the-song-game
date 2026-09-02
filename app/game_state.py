import json
from typing import Any, cast

from itsdangerous import TimestampSigner

from app.config import settings

_signer = TimestampSigner(settings.session_secret)


def serialize_session(data: dict[str, Any]) -> str:
    return _signer.sign(json.dumps(data).encode()).decode()


def deserialize_session(cookie: str) -> dict[str, Any] | None:
    try:
        unsigned = _signer.unsign(cookie.encode(), max_age=60 * 60 * 24 * 7).decode()
        return cast(dict[str, Any], json.loads(unsigned))
    except Exception:
        return None