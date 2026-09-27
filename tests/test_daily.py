from collections.abc import Iterator
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import daily
from app.main import app
from app.models import PlayableTrack
from app.services.deezer import fetch_global_chart

DAY = date(2026, 10, 5)


def _chart(n: int) -> list[PlayableTrack]:
    return [
        PlayableTrack(
            name=f"Song {i}",
            artist=f"Artist {i}",
            preview_url=f"https://dzcdn.net/preview{i}.mp3",
            duration_ms=180000,
            deezer_id=1000 + i,
        )
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def clear_daily_cache() -> Iterator[None]:
    daily._cache.clear()
    yield
    daily._cache.clear()


async def _make_client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    )


class TestBuildChallenge:
    def test_same_day_is_deterministic(self) -> None:  # noqa: ANN101
        a = daily.build_challenge(_chart(50), DAY)
        b = daily.build_challenge(_chart(50), DAY)
        assert len(a.rounds) == 5
        assert a.rounds == b.rounds

    def test_different_days_differ(self) -> None:  # noqa: ANN101
        a = daily.build_challenge(_chart(50), DAY)
        b = daily.build_challenge(_chart(50), date(2026, 10, 6))
        assert a.rounds != b.rounds

    def test_chart_order_does_not_matter(self) -> None:  # noqa: ANN101
        chart = _chart(50)
        a = daily.build_challenge(chart, DAY)
        b = daily.build_challenge(list(reversed(chart)), DAY)
        assert a.rounds == b.rounds

    def test_offsets_stay_inside_preview(self) -> None:  # noqa: ANN101
        challenge = daily.build_challenge(_chart(50), DAY)
        for r in challenge.rounds:
            assert 0 <= r.start_offset_ms <= 30000 - 2500

    def test_small_chart(self) -> None:  # noqa: ANN101
        challenge = daily.build_challenge(_chart(3), DAY)
        assert len(challenge.rounds) == 3

    def test_pool_matches_rounds(self) -> None:  # noqa: ANN101
        challenge = daily.build_challenge(_chart(50), DAY)
        assert {t.deezer_id for t in challenge.pool} == {
            r.deezer_id for r in challenge.rounds
        }

    def test_number(self) -> None:  # noqa: ANN101
        assert daily.challenge_number(daily.DAILY_EPOCH) == 1


@pytest.mark.asyncio
async def test_chart_fetched_once_per_day() -> None:
    fetch = AsyncMock(return_value=_chart(50))
    with patch("app.daily.fetch_global_chart", fetch), \
         patch("app.daily.today_brt", return_value=DAY):
        first = await daily.get_today_challenge()
        second = await daily.get_today_challenge()
    assert first is second
    assert fetch.call_count == 1


@pytest.mark.asyncio
async def test_daily_info() -> None:
    with patch("app.daily.today_brt", return_value=DAY):
        async with await _make_client() as client:
            resp = await client.get("/daily/info")
    assert resp.status_code == 200
    assert resp.json() == {
        "date": "2026-10-05",
        "number": daily.challenge_number(DAY),
    }


@pytest.mark.asyncio
async def test_daily_game_follows_planned_rounds() -> None:
    chart = _chart(50)
    expected = daily.build_challenge(chart, DAY)
    urls = {t.deezer_id: t.preview_url for t in chart}

    with patch("app.daily.fetch_global_chart", AsyncMock(return_value=chart)), \
         patch("app.daily.today_brt", return_value=DAY):
        async with await _make_client() as client:
            resp = await client.get("/daily/start")
            assert resp.status_code == 200
            data = resp.json()
            assert data["rounds_total"] == 5
            assert len(data["tracks"]) == 50  # autocomplete gets the whole chart
            assert data["daily"]["date"] == "2026-10-05"

            for i, planned in enumerate(expected.rounds):
                resp = await client.post("/round/start")
                assert resp.status_code == 200
                body = resp.json()
                assert body["preview_url"] == urls[planned.deezer_id]
                assert body["start_time_ms"] == planned.start_offset_ms

                for _ in range(5):  # use up every attempt
                    resp = await client.post("/round/skip")
                assert resp.json()["round_over"] is True
                assert resp.json()["game_over"] is (i == 4)

            resp = await client.get("/game/summary")
            assert resp.status_code == 200
            assert len(resp.json()["rounds"]) == 5


@pytest.mark.asyncio
async def test_daily_start_deezer_error() -> None:
    import httpx

    failing = AsyncMock(side_effect=httpx.ConnectError("boom"))
    with patch("app.daily.fetch_global_chart", failing), \
         patch("app.daily.today_brt", return_value=DAY):
        async with await _make_client() as client:
            resp = await client.get("/daily/start")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_fetch_global_chart_maps_fields() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: {
        "data": [
            {
                "id": 1,
                "title": "Song (feat. X)",
                "title_short": "Song",
                "artist": {"name": "Artist"},
                "preview": "https://dzcdn.net/p1.mp3",
                "duration": 200,
                "album": {"cover_medium": "https://img/1.jpg"},
            },
            {
                "id": 2,
                "title": "No Preview",
                "title_short": "No Preview",
                "artist": {"name": "Artist"},
                "preview": "",
                "duration": 200,
                "album": {},
            },
        ]
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        tracks = await fetch_global_chart()

    assert len(tracks) == 1
    assert tracks[0].name == "Song"
    assert tracks[0].duration_ms == 200000
    assert tracks[0].deezer_id == 1
    assert tracks[0].image_url == "https://img/1.jpg"
