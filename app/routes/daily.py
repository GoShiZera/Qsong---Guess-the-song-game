import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Response

from app import daily
from app.game_state import create_game_session
from app.models import GameState
from app.routes.game import set_game_cookie

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/daily/info")
async def daily_info() -> dict[str, Any]:
    """Today's challenge id, without hitting Deezer. The frontend uses it to
    check whether this browser already played today before starting."""
    day = daily.today_brt()
    return {"date": day.isoformat(), "number": daily.challenge_number(day)}


@router.get("/daily/start")
async def daily_start(response: Response) -> dict[str, Any]:
    try:
        challenge = await daily.get_today_challenge()
    except httpx.HTTPError:
        logger.error("Failed to load Deezer chart for daily challenge", exc_info=True)
        raise HTTPException(
            status_code=502, detail="Não foi possível carregar o desafio de hoje"
        ) from None

    if not challenge.rounds:
        raise HTTPException(
            status_code=404, detail="Nenhuma faixa disponível para o desafio de hoje"
        )

    state = GameState(
        playlist_id=f"daily:{challenge.date.isoformat()}",
        pool=challenge.pool,
        rounds_total=len(challenge.rounds),
        planned_rounds=challenge.rounds,
    )
    set_game_cookie(response, create_game_session(state))

    return {
        # Autocomplete gets the whole chart, not just the 5 answers.
        "tracks": [{"name": t.name, "artist": t.artist} for t in challenge.chart],
        "total": len(challenge.chart),
        "rounds_total": len(challenge.rounds),
        "daily": {"date": challenge.date.isoformat(), "number": challenge.number},
    }
