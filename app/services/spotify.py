import base64
import time
from typing import Any, cast

import httpx

from app.config import settings
from app.models import SpotifyTrack

# App token cache (Client Credentials)
_app_token_cache: dict[str, Any] = {"access_token": None, "expires_at": 0}


async def get_app_token() -> str:
    """Get app-level token via Client Credentials Flow."""
    now = time.time()
    if _app_token_cache["access_token"] and now < _app_token_cache["expires_at"] - 300:
        return cast(str, _app_token_cache["access_token"])

    credentials = f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://accounts.spotify.com/api/token",
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

    _app_token_cache["access_token"] = data["access_token"]
    _app_token_cache["expires_at"] = now + data["expires_in"]
    return cast(str, data["access_token"])


async def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    """Exchange authorization code for user access/refresh tokens."""
    credentials = f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://accounts.spotify.com/api/token",
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.spotify_redirect_uri,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())


async def refresh_user_token(refresh_token: str) -> dict[str, Any]:
    """Refresh user access token using refresh token."""
    credentials = f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://accounts.spotify.com/api/token",
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return cast(dict[str, Any], resp.json())


def get_auth_url(state: str | None = None) -> str:
    """Generate Spotify authorization URL."""
    from urllib.parse import urlencode

    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": "playlist-read-private playlist-read-collaborative",
        "show_dialog": "true",
    }
    if state:
        params["state"] = state
    return f"https://accounts.spotify.com/authorize?{urlencode(params)}"


async def _call_spotify_with_user_token(
    access_token: str,
    refresh_token: str | None,
    method: str,
    url: str,
) -> tuple[httpx.Response, str | None]:
    """Call Spotify API with user token, auto-refresh on 401."""
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.request(method, url, headers=headers, timeout=10.0)

    new_refresh_token = None
    if resp.status_code == 401 and refresh_token:
        # Try to refresh
        try:
            token_data = await refresh_user_token(refresh_token)
            new_access = token_data["access_token"]
            new_refresh = token_data.get("refresh_token", refresh_token)
            headers["Authorization"] = f"Bearer {new_access}"
            async with httpx.AsyncClient() as client:
                resp = await client.request(method, url, headers=headers, timeout=10.0)
            new_refresh_token = new_refresh
        except Exception:
            pass  # Refresh failed, return original 401

    return resp, new_refresh_token


async def fetch_user_playlists(
    access_token: str, refresh_token: str | None = None
) -> list[dict[str, Any]]:
    """Fetch user's playlists."""
    items = []
    url = "https://api.spotify.com/v1/me/playlists?limit=50"
    while url:
        resp, new_refresh = await _call_spotify_with_user_token(
            access_token, refresh_token, "GET", url
        )
        if resp.status_code == 401:
            raise ValueError("Token expirado ou inválido")
        resp.raise_for_status()
        data = resp.json()
        for pl in data.get("items", []):
            if pl.get("tracks", {}).get("total", 0) > 0:
                items.append({
                    "id": pl["id"],
                    "name": pl["name"],
                    "owner": pl["owner"]["display_name"],
                    "tracks_total": pl["tracks"]["total"],
                    "public": pl["public"],
                    "images": pl.get("images", []),
                })
        url = data.get("next")
    return items


async def _fetch_spotify_items(
    url: str,
    token: str,
    use_refresh: str | None = None,
) -> list[SpotifyTrack]:
    """Generic function to fetch tracks from a paginated Spotify endpoint."""
    tracks: list[SpotifyTrack] = []

    async with httpx.AsyncClient() as client:
        while url:
            headers = {"Authorization": f"Bearer {token}"}
            resp = await client.get(url, headers=headers, timeout=10.0)
            if resp.status_code == 404:
                raise ValueError("Recurso não encontrado ou sem acesso")
            if resp.status_code == 401 and use_refresh:
                try:
                    token_data = await refresh_user_token(use_refresh)
                    token = token_data["access_token"]
                    use_refresh = token_data.get("refresh_token", use_refresh)
                    headers["Authorization"] = f"Bearer {token}"
                    resp = await client.get(url, headers=headers, timeout=10.0)
                except Exception:
                    pass
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                # Playlist: item has nested "track" key; Album: item IS the track
                track = item.get("track") if "track" in item else item
                if not track or track.get("type") != "track":
                    continue
                artists = track.get("artists", [])
                artist_name = artists[0]["name"] if artists else "Desconhecido"
                tracks.append(
                    SpotifyTrack(
                        name=track["name"],
                        artist=artist_name,
                        spotify_id=track["id"],
                        duration_ms=track["duration_ms"],
                    )
                )

            url = data.get("next")

    return tracks


async def fetch_playlist_tracks(
    playlist_id: str,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> list[SpotifyTrack]:
    """Fetch tracks from a playlist. Uses user token if provided, else app token."""
    if access_token:
        token = access_token
        use_refresh = refresh_token
    else:
        token = await get_app_token()
        use_refresh = None

    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?limit=100"
    return await _fetch_spotify_items(url, token, use_refresh)


async def fetch_album_tracks(
    album_id: str,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> list[SpotifyTrack]:
    """Fetch tracks from an album. Uses user token if provided, else app token."""
    if access_token:
        token = access_token
        use_refresh = refresh_token
    else:
        token = await get_app_token()
        use_refresh = None

    url = f"https://api.spotify.com/v1/albums/{album_id}/tracks?limit=50"
    return await _fetch_spotify_items(url, token, use_refresh)