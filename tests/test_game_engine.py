from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import PlayableTrack


@pytest.fixture
def sample_pool() -> list[PlayableTrack]:
    return [
        PlayableTrack(
            name="Song One",
            artist="Artist A",
            preview_url="https://dzcdn.net/preview1.mp3",
            duration_ms=180000,
            deezer_id=100,
        ),
        PlayableTrack(
            name="Song Two",
            artist="Artist B",
            preview_url="https://dzcdn.net/preview2.mp3",
            duration_ms=200000,
            deezer_id=200,
        ),
        PlayableTrack(
            name="Song Three",
            artist="Artist C",
            preview_url="https://dzcdn.net/preview3.mp3",
            duration_ms=220000,
            deezer_id=300,
        ),
    ]


VALID_PLAYLIST_ID = "37i9dQZF1DXcBWIGoYBM5M"


def _get_cookie(resp: object) -> str | None:
    set_cookie = resp.headers.get("set-cookie")
    if set_cookie:
        # Extract just the cookie value part (before the first semicolon)
        # Format: "game_session=abc123; Path=/; ..."
        parts = set_cookie.split(";")
        cookie_part = parts[0].strip()
        # Extract value after '='
        if "=" in cookie_part:
            return cookie_part.split("=", 1)[1]
    return None


def _make_mock_obj(tracks: list[PlayableTrack]) -> list:
    return [
        type("Obj", (), {
            "name": t.name,
            "artist": t.artist,
            "spotify_id": f"s{i}",
            "duration_ms": t.duration_ms,
        })()
        for i, t in enumerate(tracks)
    ]


async def _complete_round(
    client: AsyncClient,
    headers: dict,
    correct: bool,
    track_name: str,
) -> dict:
    """Complete a round by making 7 attempts (6 wrong + 1 correct/skip)."""
    for attempt in range(6):
        resp = await client.post(
            "/round/guess",
            headers=headers,
            json={"guess": f"Wrong {attempt}"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    guess = track_name if correct else "Final Skip"
    resp = await client.post(
        "/round/guess",
        headers=headers,
        json={"guess": guess},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    return resp.json()


def _setup_mocks(mock_fetch: MagicMock, mock_match: MagicMock, tracks: list[PlayableTrack]) -> None:
    mock_fetch.return_value = _make_mock_obj(tracks)
    mock_match.return_value = tracks


async def _make_client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    )


@pytest.mark.asyncio
async def test_full_game_flow(sample_pool: list[PlayableTrack]) -> None:
    with patch("app.routes.game.fetch_playlist_tracks") as mock_fetch, \
         patch("app.routes.game.match_spotify_to_deezer") as mock_match:

        _setup_mocks(mock_fetch, mock_match, sample_pool)

        async with await _make_client() as client:
            resp = await client.get(
                "/game/start",
                params={"playlist_id": VALID_PLAYLIST_ID, "rounds": 3},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 3
            assert data["rounds_total"] == 3
            assert len(data["tracks"]) == 3

            cookie = _get_cookie(resp)
            assert cookie is not None
            headers = {"Cookie": f"game_session={cookie}"}

            for i in range(3):
                resp = await client.post("/round/start", headers=headers)
                assert resp.status_code == 200
                assert resp.json()["clip_duration_ms"] == 100

                track_name = sample_pool[i].name
                resp = await _complete_round(client, headers, False, track_name)
                assert resp["correct"] is False
                assert "revealed_track" in resp

                expected_game_over = (i == 2)
                assert resp["game_over"] == expected_game_over, (
                    f"Round {i}: expected game_over={expected_game_over}, "
                    f"got {resp['game_over']}"
                )

            resp = await client.get("/game/summary", headers=headers)
            assert resp.status_code == 200
            summary = resp.json()
            assert summary["acertos"] == 0
            assert summary["erros"] == 3
            assert len(summary["rounds"]) == 3


@pytest.mark.asyncio
async def test_correct_guess_ends_round_early() -> None:
    single_track_pool = [
        PlayableTrack(
            name="Only Song",
            artist="Only Artist",
            preview_url="https://dzcdn.net/preview.mp3",
            duration_ms=180000,
            deezer_id=999,
        ),
    ]

    with patch("app.routes.game.fetch_playlist_tracks") as mock_fetch, \
         patch("app.routes.game.match_spotify_to_deezer") as mock_match:

        _setup_mocks(mock_fetch, mock_match, single_track_pool)

        async with await _make_client() as client:
            resp = await client.get(
                "/game/start",
                params={"playlist_id": VALID_PLAYLIST_ID, "rounds": 1},
            )
            assert resp.status_code == 200
            cookie = _get_cookie(resp)
            headers = {"Cookie": f"game_session={cookie}"}

            resp = await client.post("/round/start", headers=headers)
            assert resp.status_code == 200

            track_name = single_track_pool[0].name
            resp = await _complete_round(client, headers, True, track_name)
            assert resp["correct"] is True
            assert "revealed_track" in resp
            assert resp["game_over"] is True


@pytest.mark.asyncio
async def test_game_over_after_rounds(sample_pool: list[PlayableTrack]) -> None:
    with patch("app.routes.game.fetch_playlist_tracks") as mock_fetch, \
         patch("app.routes.game.match_spotify_to_deezer") as mock_match:

        _setup_mocks(mock_fetch, mock_match, sample_pool)

        async with await _make_client() as client:
            resp = await client.get(
                "/game/start",
                params={"playlist_id": VALID_PLAYLIST_ID, "rounds": 2},
            )
            assert resp.status_code == 200
            cookie = _get_cookie(resp)
            headers = {"Cookie": f"game_session={cookie}"}

            # Round 1
            resp = await client.post("/round/start", headers=headers)
            assert resp.status_code == 200
            await _complete_round(client, headers, False, sample_pool[0].name)

            # Round 2
            resp = await client.post("/round/start", headers=headers)
            assert resp.status_code == 200
            await _complete_round(client, headers, False, sample_pool[1].name)

            # Game over - next round/start should fail
            resp = await client.post("/round/start", headers=headers)
            assert resp.status_code == 400
            assert "finalizada" in resp.json()["detail"]

            # Summary should work
            resp = await client.get("/game/summary", headers=headers)
            assert resp.status_code == 200
            summary = resp.json()
            assert summary["erros"] == 2
            assert summary["acertos"] == 0
            assert len(summary["rounds"]) == 2


@pytest.mark.asyncio
async def test_invalid_session() -> None:
    async with await _make_client() as client:
        resp = await client.post("/round/start")
        assert resp.status_code == 400
        assert "Sessão inválida" in resp.json()["detail"]

        resp = await client.post("/round/guess", json={"guess": "test"})
        assert resp.status_code == 400

        resp = await client.post("/round/skip")
        assert resp.status_code == 400

        resp = await client.get("/game/summary")
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_clip_duration_progression() -> None:
    track = PlayableTrack(
        name="Test Song",
        artist="Test Artist",
        preview_url="https://dzcdn.net/preview.mp3",
        duration_ms=30000,
        deezer_id=999,
    )

    with patch("app.routes.game.fetch_playlist_tracks") as mock_fetch, \
         patch("app.routes.game.match_spotify_to_deezer") as mock_match:

        _setup_mocks(mock_fetch, mock_match, [track])

        async with await _make_client() as client:
            resp = await client.get(
                "/game/start",
                params={"playlist_id": VALID_PLAYLIST_ID, "rounds": 1},
            )
            assert resp.status_code == 200
            cookie = _get_cookie(resp)
            assert cookie is not None
            headers = {"Cookie": f"game_session={cookie}"}

            resp = await client.post("/round/start", headers=headers)
            assert resp.status_code == 200
            assert resp.json()["clip_duration_ms"] == 100

            # Wrong guesses should progress through clip durations
            expected_durations = [200, 400, 800, 1600, 2000, 2500]
            for expected in expected_durations:
                resp = await client.post(
                    "/round/guess",
                    headers=headers,
                    json={"guess": "Wrong"},
                )
                assert resp.status_code == 200
                data = resp.json()
                if data["attempt"] < 6:
                    assert data["next_clip_duration_ms"] == expected


@pytest.mark.asyncio
async def test_round_history_detail(sample_pool: list[PlayableTrack]) -> None:
    with patch("app.routes.game.fetch_playlist_tracks") as mock_fetch, \
         patch("app.routes.game.match_spotify_to_deezer") as mock_match:

        _setup_mocks(mock_fetch, mock_match, sample_pool)

        async with await _make_client() as client:
            resp = await client.get(
                "/game/start",
                params={"playlist_id": VALID_PLAYLIST_ID, "rounds": 1},
            )
            assert resp.status_code == 200
            cookie = _get_cookie(resp)
            assert cookie is not None
            headers = {"Cookie": f"game_session={cookie}"}

            resp = await client.post("/round/start", headers=headers)
            for i in range(3):
                resp = await client.post(
                    "/round/guess",
                    headers=headers,
                    json={"guess": f"Wrong {i}"},
                )
                assert resp.status_code == 200

            for i in range(4):
                resp = await client.post(
                    "/round/guess",
                    headers=headers,
                    json={"guess": f"Wrong {i + 3}"},
                )
                assert resp.status_code == 200

            assert resp.json()["correct"] is False
            assert "revealed_track" in resp.json()

            resp = await client.get("/game/summary", headers=headers)
            assert resp.status_code == 200
            summary = resp.json()

            round_data = summary["rounds"][0]
            assert "track" in round_data
            assert "guesses" in round_data
            assert "correct" in round_data
            assert "completed_at" in round_data
            assert len(round_data["guesses"]) == 7
            assert round_data["guesses"][0]["attempt"] == 1
            assert round_data["guesses"][6]["attempt"] == 7
            assert round_data["correct"] is False