import logging
import random
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Body, HTTPException, Query, Request, Response

from app.config import settings
from app.game_state import (
    create_game_session,
    get_game_session,
    serialize_session,
    update_game_session,
)
from app.models import GameState, GuessRecord, RoundResult
from app.services.deezer import match_spotify_to_deezer
from app.services.spotify import (
    SpotifyAPIError,
    fetch_album_tracks,
    fetch_playlist_tracks,
    fetch_user_playlists,
    fetch_user_profile,
)

router = APIRouter()

logger = logging.getLogger(__name__)

PLAYLIST_ID_REGEX = re.compile(r"playlist/([a-zA-Z0-9]{22})")
ALBUM_ID_REGEX = re.compile(r"album/([a-zA-Z0-9]{22})")
CLIP_DURATIONS = [400, 800, 1600, 2000, 2500]


def _persist_refreshed_tokens(
    response: Response,
    session: dict[str, Any],
    token_update: dict[str, str],
) -> None:
    """If a Spotify access token was refreshed mid-request, write the new
    token pair back into the auth_session cookie. Without this, a refreshed
    token is used for the current request only and then discarded — the next
    request refreshes again from the (still valid) old refresh_token, but if
    Spotify ever rotates the refresh_token itself, the rotated value is lost
    and the user gets silently logged out.
    """
    if not token_update:
        return
    user_tokens = dict(session.get("user_tokens") or {})
    user_tokens["access_token"] = token_update["access_token"]
    user_tokens["refresh_token"] = (
        token_update.get("refresh_token") or user_tokens.get("refresh_token")
    )
    session_data = {**session, "user_tokens": user_tokens, "authenticated": True}
    response.set_cookie(
        key="auth_session",
        value=serialize_session(session_data),
        max_age=60 * 60 * 24 * 7,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


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

    # Get user tokens if available (for private playlists and Liked Songs)
    session = getattr(request.state, "session", {})
    user_tokens = session.get("user_tokens")
    access_token = user_tokens.get("access_token") if user_tokens else None
    refresh_token = user_tokens.get("refresh_token") if user_tokens else None

    # Validate access token for private resources
    if resource_type == "playlist" and spotify_id == "me:liked" and not access_token:
        raise HTTPException(status_code=401, detail="Não autenticado para acessar Músicas Curtidas")

    token_update: dict[str, str] = {}
    try:
        if resource_type == "album":
            spotify_tracks = await fetch_album_tracks(
                spotify_id, access_token, refresh_token, token_update
            )
        else:
            spotify_tracks = await fetch_playlist_tracks(
                spotify_id, access_token, refresh_token, token_update
            )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except SpotifyAPIError as e:
        raise HTTPException(status_code=500, detail=f"Erro no Spotify: {e}") from None
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        logger.error(
            "Spotify API error: status=%s, response=%s, playlist_id=%s",
            e.response.status_code,
            e.response.text[:500] if e.response.text else "empty",
            spotify_id,
            exc_info=True,
        )
        if e.response.status_code == 403:
            detail = (
                "Sem permissão para acessar esta playlist. "
                "Verifique se é pública ou se você tem acesso."
            )
            raise HTTPException(status_code=403, detail=detail) from None
        if e.response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Limite de requisições excedido. Tente novamente em alguns instantes.",
            ) from None
        raise HTTPException(
            status_code=502,
            detail=f"Erro na API do Spotify ({e.response.status_code})",
        ) from None
    except Exception as e:
        logger.error(
            "Unexpected error fetching playlist tracks: %s, playlist_id=%s",
            e,
            spotify_id,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Erro interno do servidor") from None

    _persist_refreshed_tokens(response, session, token_update)

    if not spotify_tracks:
        raise HTTPException(status_code=404, detail="Nenhuma faixa válida encontrada na playlist")

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

    set_game_cookie(response, create_game_session(state))

    return {
        "tracks": [{"name": t.name, "artist": t.artist} for t in pool],
        "total": len(pool),
        "rounds_total": rounds_total,
    }


def set_game_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key="game_session",
        value=session_id,
        max_age=60 * 60 * 24 * 7,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/round/start")
async def round_start(request: Request, response: Response) -> dict[str, Any]:
    state = await _get_game_state(request)
    if state is None:
        raise HTTPException(status_code=400, detail="Sessão inválida ou expirada")

    if state.round_atual >= state.rounds_total:
        raise HTTPException(status_code=400, detail="Partida já finalizada")

    if state.planned_rounds is not None:
        # Daily challenge: fixed track and clip offset, same for every player.
        planned = state.planned_rounds[state.round_atual]
        track = next(t for t in state.pool if t.deezer_id == planned.deezer_id)
        start_offset = planned.start_offset_ms
    else:
        played_tracks = {r.track.deezer_id for r in state.round_history}
        available = [
            t for t in state.pool if t.deezer_id not in played_tracks and t.preview_url
        ]
        if not available:
            raise HTTPException(status_code=400, detail="Nenhuma faixa com preview disponível")

        track = random.choice(available)
        # Fix: use preview duration (max 30s = 30000ms) instead of full track duration
        preview_duration = min(track.duration_ms, 30000)
        max_offset = max(0, preview_duration - 2500)
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


def _record_attempt(
    state: GameState, guess_text: str, correct: bool
) -> tuple[bool, int, bool, dict[str, Any] | None]:
    """Record one guess/skip attempt against the current round and advance
    the round/game state accordingly. Shared by /round/guess and
    /round/skip, which only differ in whether the attempt was correct and
    what raw guess text (if any) gets stored in the history.

    Returns (round_over, attempt_number, game_over, revealed_track_dump).
    """
    assert state.current_track is not None
    clip_duration = CLIP_DURATIONS[state.attempt]
    state.guess_history.append(
        GuessRecord(
            attempt=state.attempt + 1,
            guess=guess_text,
            correct=correct,
            clip_duration_ms=clip_duration,
        )
    )

    # A round ends on a correct guess or once every fixed attempt has been used.
    round_over = correct or state.attempt >= 4
    attempt_number = state.attempt + 1

    if round_over:
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
        # Check if game is over: either all rounds played or no more tracks available
        played_ids = {r.track.deezer_id for r in state.round_history}
        remaining = [t for t in state.pool if t.deezer_id not in played_ids and t.preview_url]
        game_over = state.round_atual >= state.rounds_total or len(remaining) == 0
        revealed: dict[str, Any] | None = (
            revealed_track.model_dump() if revealed_track else None
        )
    else:
        state.attempt += 1
        game_over = False
        revealed = None

    state.updated_at = datetime.now(UTC)
    return round_over, attempt_number, game_over, revealed


@router.post("/round/guess")
async def round_guess(
    request: Request,
    response: Response,
    guess: str = Body(..., embed=True),
) -> dict[str, Any]:
    state = await _get_game_state(request)
    if state is None or state.current_track is None:
        raise HTTPException(status_code=400, detail="Sessão inválida ou nenhum round ativo")

    normalized_guess = _normalize(guess)
    expected_name = _normalize(state.current_track.name)
    expected_full = _normalize(f"{state.current_track.name} - {state.current_track.artist}")
    correct = normalized_guess == expected_name or normalized_guess == expected_full

    round_over, attempt_number, game_over, revealed = _record_attempt(state, guess, correct)

    session_id = request.cookies.get("game_session")
    assert session_id is not None
    update_game_session(session_id, state)

    result: dict[str, Any] = {
        "correct": correct,
        "attempt": attempt_number,
        "round_over": round_over,
        "game_over": game_over,
    }
    if not round_over:
        result["next_clip_duration_ms"] = CLIP_DURATIONS[state.attempt]
    if revealed:
        result["revealed_track"] = revealed

    return result


@router.post("/round/skip")
async def round_skip(request: Request, response: Response) -> dict[str, Any]:
    state = await _get_game_state(request)
    if state is None or state.current_track is None:
        raise HTTPException(status_code=400, detail="Sessão inválida ou nenhum round ativo")

    # Skip just advances the attempt without ever being "correct".
    round_over, attempt_number, game_over, revealed = _record_attempt(state, "", False)

    session_id = request.cookies.get("game_session")
    assert session_id is not None
    update_game_session(session_id, state)

    result: dict[str, Any] = {
        "correct": False,
        "attempt": attempt_number,
        "round_over": round_over,
        "game_over": game_over,
    }
    if not round_over:
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


@router.get("/user/profile")
async def get_user_profile_route(request: Request, response: Response) -> dict[str, Any]:
    session = getattr(request.state, "session", {})
    user_tokens = session.get("user_tokens")
    if not user_tokens:
        raise HTTPException(status_code=401, detail="Não autenticado")

    access_token = user_tokens.get("access_token")
    refresh_token = user_tokens.get("refresh_token")

    token_update: dict[str, str] = {}
    try:
        profile = await fetch_user_profile(access_token, refresh_token, token_update)
        _persist_refreshed_tokens(response, session, token_update)
        return profile
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None
    except SpotifyAPIError as e:
        raise HTTPException(status_code=500, detail=f"Erro no Spotify: {e}") from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Erro interno do servidor") from None


@router.get("/user/playlists")
async def get_user_playlists(request: Request, response: Response) -> list[dict[str, Any]]:
    session = getattr(request.state, "session", {})
    user_tokens = session.get("user_tokens")
    if not user_tokens:
        raise HTTPException(status_code=401, detail="Não autenticado")

    access_token = user_tokens.get("access_token")
    refresh_token = user_tokens.get("refresh_token")

    token_update: dict[str, str] = {}
    try:
        playlists = await fetch_user_playlists(access_token, refresh_token, token_update)
        _persist_refreshed_tokens(response, session, token_update)
        # Ensure all playlists have tracks_total field
        for pl in playlists:
            if "tracks_total" not in pl or pl["tracks_total"] is None:
                pl["tracks_total"] = 0
        return playlists
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None
    except SpotifyAPIError as e:
        raise HTTPException(status_code=500, detail=f"Erro no Spotify: {e}") from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Erro interno do servidor") from None