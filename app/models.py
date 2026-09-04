from datetime import UTC, datetime

from pydantic import BaseModel, Field


class SpotifyTrack(BaseModel):
    name: str
    artist: str
    spotify_id: str
    duration_ms: int
    preview_url: str | None = None
    image_url: str | None = None


class DeezerTrack(BaseModel):
    id: int
    title: str
    artist_name: str
    preview_url: str
    duration: int
    rank: int
    image_url: str | None = None


class PlayableTrack(BaseModel):
    name: str
    artist: str
    preview_url: str
    duration_ms: int
    deezer_id: int
    image_url: str | None = None


class GameConfig(BaseModel):
    playlist_id: str
    rounds_total: int | None = None


class GuessRecord(BaseModel):
    attempt: int = Field(ge=1, le=7)
    guess: str
    correct: bool
    clip_duration_ms: int


class RoundResult(BaseModel):
    track: PlayableTrack
    guesses: list[GuessRecord]
    correct: bool
    completed_at: datetime


class GameState(BaseModel):
    playlist_id: str
    pool: list[PlayableTrack]
    rounds_total: int
    round_atual: int = 0
    current_track: PlayableTrack | None = None
    start_offset_ms: int = 0
    attempt: int = 0
    guess_history: list[GuessRecord] = []
    round_history: list[RoundResult] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))