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
        "scope": " ".join([
            "playlist-read-private",
            "playlist-read-collaborative",
            "user-read-private",
            "user-library-read",
        ]),
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
) -> tuple[httpx.Response, str | None, str | None]:
    """Call Spotify API with user token, auto-refresh on 401.
    Returns: (response, new_access_token, new_refresh_token)"""
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.request(method, url, headers=headers, timeout=10.0)

    new_access_token = None
    new_refresh_token = None
    if resp.status_code == 401 and refresh_token:
        # Try to refresh
        try:
            token_data = await refresh_user_token(refresh_token)
            new_access_token = token_data["access_token"]
            new_refresh_token = token_data.get("refresh_token", refresh_token)
            headers["Authorization"] = f"Bearer {new_access_token}"
            async with httpx.AsyncClient() as client:
                resp = await client.request(method, url, headers=headers, timeout=10.0)
        except Exception:
            pass  # Refresh failed, return original 401

    return resp, new_access_token, new_refresh_token


async def fetch_user_profile(
    access_token: str, refresh_token: str | None = None
) -> dict[str, Any]:
    """Fetch authenticated user's profile info (name, avatar)."""
    url = "https://api.spotify.com/v1/me"
    resp, new_access, new_refresh = await _call_spotify_with_user_token(
        access_token, refresh_token, "GET", url
    )
    if resp.status_code == 401:
        raise ValueError("Token expirado ou inválido")
    resp.raise_for_status()
    data = resp.json()
    images = data.get("images", [])
    avatar_url = images[0].get("url") if images else None
    return {
        "id": data.get("id"),
        "display_name": data.get("display_name") or "Usuário Spotify",
        "avatar_url": avatar_url,
    }


async def fetch_user_playlists(
    access_token: str, refresh_token: str | None = None
) -> list[dict[str, Any]]:
    """Fetch user's playlists."""
    items = []
    url = "https://api.spotify.com/v1/me/playlists?limit=50"
    current_access = access_token
    current_refresh = refresh_token
    while url:
        resp, new_access, new_refresh = await _call_spotify_with_user_token(
            current_access, current_refresh, "GET", url
        )
        if resp.status_code == 401:
            raise ValueError("Token expirado ou inválido")
        # Update tokens if they were refreshed
        if new_access:
            current_access = new_access
        if new_refresh:
            current_refresh = new_refresh
        resp.raise_for_status()
        data = resp.json()
        for pl in data.get("items", []):
            if not pl:
                continue
            tracks_info = pl.get("tracks")
            total = tracks_info.get("total", 0) if isinstance(tracks_info, dict) else 0
            items.append({
                "id": pl["id"],
                "name": pl.get("name", "Playlist sem nome"),
                "owner": pl.get("owner", {}).get("display_name", "Spotify"),
                "tracks_total": total,
                "public": pl.get("public", False),
                "images": pl.get("images", []),
            })
        url = data.get("next")
    # Check for Liked Songs (Músicas Curtidas)
    try:
        liked_resp, _, _ = await _call_spotify_with_user_token(
            current_access, current_refresh, "GET", "https://api.spotify.com/v1/me/tracks?limit=1"
        )
        if liked_resp.status_code == 200:
            liked_data = liked_resp.json()
            liked_total = liked_data.get("total", 0)
            if liked_total > 0:
                items.insert(0, {
                    "id": "me:liked",
                    "name": "Músicas Curtidas (Liked Songs)",
                    "owner": "Você",
                    "tracks_total": liked_total,
                    "public": False,
                    "images": [],
                })
    except Exception:
        pass
    return items


class SpotifyAPIError(Exception):
    """Custom exception for Spotify API errors."""
    def __init__(self: "SpotifyAPIError", message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


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
            if resp.status_code == 401:
                raise ValueError("Token expirado ou inválido")
            if resp.status_code >= 500:
                raise SpotifyAPIError("Erro no servidor do Spotify", resp.status_code)
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
                        preview_url=track.get("preview_url"),
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
    # Handle special "Liked Songs" playlist
    if playlist_id == "me:liked":
        if not access_token:
            raise ValueError("Acesso a Músicas Curtidas requer autenticação do usuário")
        token = access_token
        use_refresh = refresh_token
        url = "https://api.spotify.com/v1/me/tracks?limit=50"
        return await _fetch_spotify_items(url, token, use_refresh)

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