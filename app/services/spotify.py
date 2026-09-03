import base64
import time
from typing import Any, cast

import httpx

from app.config import settings
from app.models import SpotifyTrack

_token_cache: dict[str, Any] = {"access_token": None, "expires_at": 0}


async def get_app_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 300:
        return cast(str, _token_cache["access_token"])

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

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + data["expires_in"]
    return cast(str, data["access_token"])


async def fetch_playlist_tracks(playlist_id: str) -> list[SpotifyTrack]:
    token = await get_app_token()
    tracks: list[SpotifyTrack] = []
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?limit=100"

    async with httpx.AsyncClient() as client:
        while url:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            if resp.status_code == 404:
                raise ValueError("Playlist não encontrada ou não pública")
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                track = item.get("track")
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