import random
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response

from app.config import settings
from app.game_state import (
    create_game_session,
    get_game_session,
    update_game_session,
)
from app.models import GameState, GuessRecord, RoundResult
from app.services.deezer import match_spotify_to_deezer
from app.services.spotify import fetch_album_tracks, fetch_playlist_tracks, fetch_user_playlists

router = APIRouter()

PLAYLIST_ID_REGEX = re.compile(r"playlist/([a-zA-Z0-9]{22})")
ALBUM_ID_REGEX = re.compile(r"album/([a-zA-Z0-9]{22})")
CLIP_DURATIONS = [100, 200, 400, 800, 1600, 2000, 2500]


def extract_spotify_id(input_str: str) -> tuple[str, str] | None:
    """Extract Spotify ID and type (playlist/album) from URL or raw ID."""
    # Try playlist URL
    match = PLAYLIST_ID_REGEX.search(input_str)
    if match:
        return match.group(1), "playlist"
    # Try album URL
    match = ALBUM_ID_REGEX.search(input_str)
    if match:
        return match.group(1), "album"
    # Try raw ID (22 chars)
    if re.fullmatch(r"[a-zA-Z0-9]{22}", input_str):
        return input_str, "playlist"  # default to playlist for raw ID
    return None


def _normalize(s: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", s.lower().strip())
        if unicodedata.category(c) != "Mn"
    )


@router.get("/game/start")
async def game_start(
    request: Request,
    response: Response,
    playlist_id: str | None = Query(None),
    url: str | None = Query(None),
    rounds: int | None = Query(None, ge=1),
) -> dict[str, Any]:
    raw_id = playlist_id or url
    if not raw_id:
        raise HTTPException(status_code=400, detail="Forneça playlist_id, album_id ou url")

    extracted = extract_spotify_id(raw_id)
    if not extracted:
        raise HTTPException(status_code=400, detail="ID de playlist/álbum inválido")

    spotify_id, resource_type = extracted

    try:
        if resource_type == "album":
            spotify_tracks = await fetch_album_tracks(spotify_id)
        else:
            spotify_tracks = await fetch_playlist_tracks(spotify_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception:
        raise HTTPException(status_code=502, detail="Erro ao buscar no Spotify") from None

    if not spotify_tracks:
        raise HTTPException(status_code=404, detail="Nenhuma faixa válida encontrada")

    pool = await match_spotify_to_deezer(spotify_tracks)

    if not pool:
        raise HTTPException(
            status_code=404,
            detail="Nenhuma faixa com preview disponível (Spotify ou Deezer)",
        )

    rounds_total = rounds or len(pool)
    if rounds_total > len(pool):
        rounds_total = len(pool)

    state = GameState(
        playlist_id=spotify_id,
        pool=pool,
        rounds_total=rounds_total,
    )

    session_id = create_game_session(state)
    response.set_cookie(
        key="game_session",
        value=session_id,
        max_age=60 * 60 * 24 * 7,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )

    return {
        "tracks": [{"name": t.name, "artist": t.artist} for t in pool],
        "total": len(pool),
        "rounds_total": rounds_total,
    }


@router.post("/round/start")
async def round_start(request: Request, response: Response) -> dict[str, Any]:
    state = await _get_game_state(request)
    if state is None:
        raise HTTPException(status_code=400, detail="Sessão inválida ou expirada")

    if state.round_atual >= state.rounds_total:
        raise HTTPException(status_code=400, detail="Partida já finalizada")

    played_tracks = {r.track.deezer_id for r in state.round_history}
    available = [t for t in state.pool if t.deezer_id not in played_tracks and t.preview_url]
    if not available:
        raise HTTPException(status_code=400, detail="Nenhuma faixa com preview disponível")

    track = random.choice(available)
    max_offset = max(0, track.duration_ms - 2500)
    start_offset = random.randint(0, max_offset)

    state.current_track = track
    state.start_offset_ms = start_offset
    state.attempt = 0
    state.guess_history = []
    state.updated_at = datetime.now(UTC)

    session_id = request.cookies.get("game_session")
    assert session_id is not None
    update_game_session(session_id, state)

    return {
        "preview_url": track.preview_url,
        "start_time_ms": start_offset,
        "clip_duration_ms": CLIP_DURATIONS[0],
    }


@router.post("/round/guess")
async def round_guess(
    request: Request,
    response: Response,
    guess: str = Body(..., embed=True),
) -> dict[str, Any]:
    state = await _get_game_state(request)
    if state is None or state.current_track is None:
        raise HTTPException(status_code=400, detail="Sessão inválida ou nenhum round ativo")

    correct = _normalize(guess) == _normalize(state.current_track.name)
    clip_duration = CLIP_DURATIONS[state.attempt]

    state.guess_history.append(
        GuessRecord(
            attempt=state.attempt + 1,
            guess=guess,
            correct=correct,
            clip_duration_ms=clip_duration,
        )
    )

    if correct or state.attempt >= 6:
        revealed_track = state.current_track
        state.round_history.append(
            RoundResult(
                track=revealed_track,
                guesses=state.guess_history.copy(),
                correct=correct,
                completed_at=datetime.now(UTC),
            )
        )
        state.round_atual += 1
        state.current_track = None
        state.attempt = 0
        state.guess_history = []
        game_over = state.round_atual >= state.rounds_total
        revealed: dict[str, Any] | None = (
            revealed_track.model_dump() if revealed_track else None
        )
    else:
        state.attempt += 1
        game_over = False
        revealed = None

    state.updated_at = datetime.now(UTC)

    session_id = request.cookies.get("game_session")
    assert session_id is not None
    update_game_session(session_id, state)

    result: dict[str, Any] = {
        "correct": correct,
        "attempt": state.attempt,
        "game_over": game_over,
    }
    if state.attempt < 7 and not correct:
        result["next_clip_duration_ms"] = CLIP_DURATIONS[state.attempt]
    if revealed:
        result["revealed_track"] = revealed

    return result


@router.post("/round/skip")
async def round_skip(request: Request, response: Response) -> dict[str, Any]:
    state = await _get_game_state(request)
    if state is None or state.current_track is None:
        raise HTTPException(status_code=400, detail="Sessão inválida ou nenhum round ativo")

    # Skip just advances the attempt without checking correctness
    clip_duration = CLIP_DURATIONS[state.attempt]
    state.guess_history.append(
        GuessRecord(
            attempt=state.attempt + 1,
            guess="",
            correct=False,
            clip_duration_ms=clip_duration,
        )
    )

    if state.attempt >= 6:
        # Round ends after 7 attempts (0-indexed, so attempt 6 is the 7th)
        state.round_history.append(
            RoundResult(
                track=state.current_track,
                guesses=state.guess_history.copy(),
                correct=False,
                completed_at=datetime.now(UTC),
            )
        )
        revealed_track = state.current_track
        state.round_atual += 1
        state.current_track = None
        state.attempt = 0
        state.guess_history = []
        game_over = state.round_atual >= state.rounds_total
        revealed: dict[str, Any] | None = (
            revealed_track.model_dump() if revealed_track else None
        )
    else:
        state.attempt += 1
        game_over = False
        revealed = None

    state.updated_at = datetime.now(UTC)

    session_id = request.cookies.get("game_session")
    assert session_id is not None
    update_game_session(session_id, state)

    result: dict[str, Any] = {
        "correct": False,
        "attempt": state.attempt,
        "game_over": game_over,
    }
    if state.attempt < 7 and not game_over:
        result["next_clip_duration_ms"] = CLIP_DURATIONS[state.attempt]
    if revealed:
        result["revealed_track"] = revealed

    return result


@router.get("/game/summary")
async def game_summary(request: Request) -> dict[str, Any]:
    state = await _get_game_state(request)
    if state is None:
        raise HTTPException(status_code=400, detail="Sessão inválida ou expirada")

    acertos = sum(1 for r in state.round_history if r.correct)
    erros = len(state.round_history) - acertos

    return {
        "acertos": acertos,
        "erros": erros,
        "rounds": [r.model_dump() for r in state.round_history],
    }


async def _get_game_state(request: Request) -> GameState | None:
    session_id = request.cookies.get("game_session")
    if not session_id:
        return None
    return get_game_session(session_id)


@router.get("/user/playlists")
async def get_user_playlists(request: Request) -> list[dict[str, Any]]:
    session = getattr(request.state, "session", {})
    user_tokens = session.get("user_tokens")
    if not user_tokens:
        raise HTTPException(status_code=401, detail="Não autenticado")

    access_token = user_tokens.get("access_token")
    refresh_token = user_tokens.get("refresh_token")

    try:
        playlists = await fetch_user_playlists(access_token, refresh_token)
        return playlists
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao buscar playlists: {e}") from None