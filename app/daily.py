"""Daily challenge: the same 5 tracks (same order, same clip offsets) for
every player on a given day, drawn from Deezer's global top-tracks chart."""

import asyncio
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.models import PlannedRound, PlayableTrack
from app.services.deezer import fetch_global_chart

# Brasília time. Brazil has had no DST since 2019, so a fixed offset is
# enough (and avoids needing the tzdata package for zoneinfo on Windows).
BRT = timezone(timedelta(hours=-3))

# Challenge #1. The challenge number is shown in the shared result text.
DAILY_EPOCH = date(2026, 9, 27)

DAILY_ROUNDS = 5
_MAX_CLIP_MS = 2500
_PREVIEW_MS = 30000


@dataclass(frozen=True)
class DailyChallenge:
    date: date
    number: int
    chart: list[PlayableTrack]  # full chart, used for the autocomplete
    rounds: list[PlannedRound]  # the tracks actually played, in order

    @property
    def pool(self) -> list[PlayableTrack]:  # noqa: ANN101
        ids = {r.deezer_id for r in self.rounds}
        return [t for t in self.chart if t.deezer_id in ids]


def today_brt() -> date:
    return datetime.now(BRT).date()


def challenge_number(day: date) -> int:
    return (day - DAILY_EPOCH).days + 1


def build_challenge(chart: list[PlayableTrack], day: date) -> DailyChallenge:
    """Deterministically pick the day's tracks and clip offsets.

    The chart is sorted by Deezer id before sampling so the order the API
    happens to return tracks in can't change the result.
    """
    rng = random.Random(f"qsong-daily-{day.isoformat()}")
    candidates = sorted(chart, key=lambda t: t.deezer_id)
    picked = rng.sample(candidates, min(DAILY_ROUNDS, len(candidates)))
    rounds = [
        PlannedRound(
            deezer_id=t.deezer_id,
            start_offset_ms=rng.randint(
                0, max(0, min(t.duration_ms, _PREVIEW_MS) - _MAX_CLIP_MS)
            ),
        )
        for t in picked
    ]
    return DailyChallenge(date=day, number=challenge_number(day), chart=chart, rounds=rounds)


# The chart is fetched once per day on first request and frozen in memory,
# so every player that day gets the same challenge even if the live chart
# moves. Caveat: a server restart mid-day re-fetches it, and if the chart
# has changed by then, the draw may differ.
_cache: dict[date, DailyChallenge] = {}
_lock = asyncio.Lock()


async def get_today_challenge() -> DailyChallenge:
    day = today_brt()
    async with _lock:
        challenge = _cache.get(day)
        if challenge is None:
            chart = await fetch_global_chart()
            challenge = build_challenge(chart, day)
            _cache.clear()
            _cache[day] = challenge
        return challenge
