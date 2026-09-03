from datetime import datetime

from _pytest.monkeypatch import MonkeyPatch

from app.game_state import (
    deserialize_game_state,
    deserialize_session,
    serialize_game_state,
    serialize_session,
)
from app.models import GameState, GuessRecord, PlayableTrack, RoundResult


def test_session_serialization_roundtrip() -> None:
    original = {"user_id": "123", "tokens": {"access": "abc", "refresh": "def"}}
    cookie = serialize_session(original)
    restored = deserialize_session(cookie)
    assert restored == original


def test_session_tampering_returns_none() -> None:
    original = {"foo": "bar"}
    cookie = serialize_session(original)
    tampered = cookie[:-5] + "xxxxx"
    assert deserialize_session(tampered) is None


def test_session_expired_returns_none(monkeypatch: MonkeyPatch) -> None:
    from itsdangerous import TimestampSigner

    from app.config import settings

    signer = TimestampSigner(settings.session_secret)
    _ = signer.sign(b'{"expired": true}').decode()
    assert deserialize_session("invalid.cookie.value") is None


def test_game_state_serialization_roundtrip() -> None:
    track = PlayableTrack(
        name="Test Song",
        artist="Test Artist",
        preview_url="https://example.com/preview.mp3",
        duration_ms=180000,
        deezer_id=12345,
    )
    state = GameState(
        playlist_id="playlist123",
        pool=[track],
        rounds_total=5,
        round_atual=1,
        current_track=track,
        start_offset_ms=5000,
        attempt=2,
        guess_history=[
            GuessRecord(attempt=1, guess="Wrong", correct=False, clip_duration_ms=100),
            GuessRecord(attempt=2, guess="Test Song", correct=True, clip_duration_ms=200),
        ],
        round_history=[
            RoundResult(
                track=track,
                guesses=[],
                correct=True,
                completed_at=datetime.utcnow(),
            )
        ],
    )

    cookie = serialize_game_state(state)
    restored = deserialize_game_state(cookie)

    assert restored is not None
    assert restored.playlist_id == "playlist123"
    assert restored.rounds_total == 5
    assert restored.round_atual == 1
    assert restored.attempt == 2
    assert len(restored.pool) == 1
    assert restored.pool[0].name == "Test Song"
    assert len(restored.guess_history) == 2
    assert len(restored.round_history) == 1


def test_game_state_tampering_returns_none() -> None:
    track = PlayableTrack(
        name="Test",
        artist="Artist",
        preview_url="https://example.com/preview.mp3",
        duration_ms=180000,
        deezer_id=1,
    )
    state = GameState(playlist_id="p1", pool=[track], rounds_total=1)
    cookie = serialize_game_state(state)
    tampered = cookie[:-5] + "xxxxx"
    assert deserialize_game_state(tampered) is None


def test_game_state_invalid_json_returns_none() -> None:
    from itsdangerous import TimestampSigner

    from app.config import settings

    signer = TimestampSigner(settings.session_secret)
    invalid_cookie = signer.sign(b"not json").decode()
    assert deserialize_game_state(invalid_cookie) is None