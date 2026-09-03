from unittest.mock import AsyncMock, patch

import pytest
from _pytest.monkeypatch import MonkeyPatch

from app.services.spotify import _token_cache, fetch_playlist_tracks, get_app_token


@pytest.fixture(autouse=True)
def clear_token_cache() -> None:
    _token_cache.clear()
    _token_cache["access_token"] = None
    _token_cache["expires_at"] = 0
    yield
    _token_cache.clear()
    _token_cache["access_token"] = None
    _token_cache["expires_at"] = 0


@pytest.mark.asyncio
async def test_get_app_token_caches(monkeypatch: MonkeyPatch) -> None:
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: {"access_token": "test_token", "expires_in": 3600}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        token1 = await get_app_token()
        token2 = await get_app_token()

    assert token1 == "test_token"
    assert token2 == "test_token"
    assert mock_client.post.call_count == 1


@pytest.mark.asyncio
async def test_fetch_playlist_tracks_success(monkeypatch: MonkeyPatch) -> None:
    mock_token_resp = AsyncMock()
    mock_token_resp.raise_for_status = lambda: None
    mock_token_resp.json = lambda: {"access_token": "test_token", "expires_in": 3600}

    mock_tracks_resp = AsyncMock()
    mock_tracks_resp.raise_for_status = lambda: None
    mock_tracks_resp.json = lambda: {
        "items": [
            {
                "track": {
                    "id": "track1",
                    "name": "Song One",
                    "artists": [{"name": "Artist A"}],
                    "duration_ms": 180000,
                    "type": "track",
                }
            },
            {
                "track": {
                    "id": "track2",
                    "name": "Song Two",
                    "artists": [{"name": "Artist B"}],
                    "duration_ms": 200000,
                    "type": "track",
                }
            },
        ],
        "next": None,
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_token_resp)
    mock_client.get = AsyncMock(return_value=mock_tracks_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        tracks = await fetch_playlist_tracks("playlist123")

    assert len(tracks) == 2
    assert tracks[0].name == "Song One"
    assert tracks[0].artist == "Artist A"
    assert tracks[0].spotify_id == "track1"
    assert tracks[1].name == "Song Two"
    assert tracks[1].artist == "Artist B"


@pytest.mark.asyncio
async def test_fetch_playlist_tracks_404(monkeypatch: MonkeyPatch) -> None:
    mock_token_resp = AsyncMock()
    mock_token_resp.raise_for_status = lambda: None
    mock_token_resp.json = lambda: {"access_token": "test_token", "expires_in": 3600}

    mock_tracks_resp = AsyncMock()
    mock_tracks_resp.status_code = 404
    mock_tracks_resp.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_token_resp)
    mock_client.get = AsyncMock(return_value=mock_tracks_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ValueError, match="Playlist não encontrada"):
            await fetch_playlist_tracks("invalid_playlist")