from unittest.mock import AsyncMock, patch

import pytest

from app.models import DeezerTrack, SpotifyTrack
from app.services.deezer import (
    _artist_matches,
    _select_best_match,
    match_spotify_to_deezer,
    search_track,
)


class TestArtistMatching:
    def test_exact_match(self) -> None:  # noqa: ANN101
        assert _artist_matches("Artist A", "Artist A") is True

    def test_case_insensitive(self) -> None:  # noqa: ANN101
        assert _artist_matches("artist a", "ARTIST A") is True

    def test_substring_expected_in_found(self) -> None:  # noqa: ANN101
        assert _artist_matches("Artist", "Artist A") is True

    def test_substring_found_in_expected(self) -> None:  # noqa: ANN101
        assert _artist_matches("Artist A", "Artist") is True

    def test_no_match(self) -> None:  # noqa: ANN101
        assert _artist_matches("Artist A", "Artist B") is False

    def test_whitespace_handling(self) -> None:  # noqa: ANN101
        assert _artist_matches(" Artist A ", "Artist A") is True


class TestSelectBestMatch:
    def test_empty_list_returns_none(self) -> None:  # noqa: ANN101
        assert _select_best_match("Artist A", []) is None

    def test_filters_by_artist(self) -> None:  # noqa: ANN101
        candidates = [
            DeezerTrack(
                id=1,
                title="Song",
                artist_name="Artist A",
                preview_url="",
                duration=180,
                rank=100,
            ),
            DeezerTrack(
                id=2,
                title="Song",
                artist_name="Artist B",
                preview_url="",
                duration=180,
                rank=200,
            ),
        ]
        best = _select_best_match("Artist A", candidates)
        assert best is not None
        assert best.artist_name == "Artist A"
        assert best.rank == 100

    def test_picks_highest_rank(self) -> None:  # noqa: ANN101
        candidates = [
            DeezerTrack(
                id=1,
                title="Song",
                artist_name="Artist A",
                preview_url="",
                duration=180,
                rank=100,
            ),
            DeezerTrack(
                id=2,
                title="Song",
                artist_name="Artist A",
                preview_url="",
                duration=180,
                rank=300,
            ),
            DeezerTrack(
                id=3,
                title="Song",
                artist_name="Artist A",
                preview_url="",
                duration=180,
                rank=200,
            ),
        ]
        best = _select_best_match("Artist A", candidates)
        assert best is not None
        assert best.rank == 300

    def test_returns_none_if_no_artist_match(self) -> None:  # noqa: ANN101
        candidates = [
            DeezerTrack(
                id=1,
                title="Song",
                artist_name="Artist B",
                preview_url="",
                duration=180,
                rank=500,
            ),
        ]
        assert _select_best_match("Artist A", candidates) is None


@pytest.mark.asyncio
async def test_search_track_success() -> None:
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {
        "data": [
            {
                "id": 123,
                "title": "Test Song",
                "artist": {"name": "Test Artist"},
                "preview": "https://example.com/preview.mp3",
                "duration": 180,
                "rank": 1000,
            }
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await search_track("Test Artist", "Test Song")

    assert len(results) == 1
    assert results[0].id == 123
    assert results[0].title == "Test Song"
    assert results[0].artist_name == "Test Artist"
    assert results[0].preview_url == "https://example.com/preview.mp3"


@pytest.mark.asyncio
async def test_search_track_empty_results() -> None:
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"data": []}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await search_track("Unknown", "Unknown")

    assert results == []


@pytest.mark.asyncio
async def test_search_track_rate_limit_retry() -> None:
    mock_resp_429 = AsyncMock()
    mock_resp_429.status_code = 429
    mock_resp_429.headers = {"Retry-After": "0"}

    mock_resp_ok = AsyncMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.json = lambda: {
        "data": [
            {
                "id": 1,
                "title": "Song",
                "artist": {"name": "Artist"},
                "preview": "https://example.com/preview.mp3",
                "duration": 180,
                "rank": 100,
            }
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[mock_resp_429, mock_resp_ok])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await search_track("Artist", "Song")

    assert len(results) == 1
    assert mock_client.get.call_count == 2


@pytest.mark.asyncio
async def test_match_spotify_to_deezer() -> None:
    spotify_tracks = [
        SpotifyTrack(name="Song One", artist="Artist A", spotify_id="s1", duration_ms=180000),
        SpotifyTrack(name="Song Two", artist="Artist B", spotify_id="s2", duration_ms=200000),
    ]

    deezer_results_1 = [
        DeezerTrack(
            id=100,
            title="Song One",
            artist_name="Artist A",
            preview_url="https://dzcdn.net/preview1.mp3",
            duration=180,
            rank=500,
        )
    ]
    deezer_results_2 = [
        DeezerTrack(
            id=200,
            title="Song Two",
            artist_name="Artist B",
            preview_url="https://dzcdn.net/preview2.mp3",
            duration=200,
            rank=600,
        )
    ]

    with patch(
        "app.services.deezer.search_track",
        side_effect=[deezer_results_1, deezer_results_2],
    ):
        playable = await match_spotify_to_deezer(spotify_tracks)

    assert len(playable) == 2
    assert playable[0].name == "Song One"
    assert playable[0].preview_url == "https://dzcdn.net/preview1.mp3"
    assert playable[0].deezer_id == 100
    assert playable[1].name == "Song Two"
    assert playable[1].preview_url == "https://dzcdn.net/preview2.mp3"
    assert playable[1].deezer_id == 200


@pytest.mark.asyncio
async def test_match_spotify_to_deezer_filters_no_preview() -> None:
    spotify_tracks = [
        SpotifyTrack(name="Song", artist="Artist", spotify_id="s1", duration_ms=180000),
    ]

    deezer_results = [
        DeezerTrack(
            id=100,
            title="Song",
            artist_name="Artist",
            preview_url="",
            duration=180,
            rank=500,
        )
    ]

    with patch("app.services.deezer.search_track", return_value=deezer_results):
        playable = await match_spotify_to_deezer(spotify_tracks)

    assert playable == []


@pytest.mark.asyncio
async def test_match_spotify_to_deezer_filters_artist_mismatch() -> None:
    spotify_tracks = [
        SpotifyTrack(name="Song", artist="Artist A", spotify_id="s1", duration_ms=180000),
    ]

    deezer_results = [
        DeezerTrack(
            id=100,
            title="Song",
            artist_name="Artist B",
            preview_url="https://dzcdn.net/preview.mp3",
            duration=180,
            rank=500,
        )
    ]

    with patch("app.services.deezer.search_track", return_value=deezer_results):
        playable = await match_spotify_to_deezer(spotify_tracks)

    assert playable == []


@pytest.mark.asyncio
async def test_match_spotify_to_deezer_handles_exceptions() -> None:
    spotify_tracks = [
        SpotifyTrack(name="Song", artist="Artist", spotify_id="s1", duration_ms=180000),
    ]

    with patch("app.services.deezer.search_track", side_effect=Exception("Network error")):
        playable = await match_spotify_to_deezer(spotify_tracks)

    assert playable == []