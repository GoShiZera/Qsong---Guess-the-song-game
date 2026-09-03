import asyncio
import random

import httpx

from app.models import DeezerTrack, PlayableTrack, SpotifyTrack

_DEEZER_SEARCH_URL = "https://api.deezer.com/search"
_SEMAPHORE = asyncio.Semaphore(10)
_MAX_RETRIES = 3
_BASE_DELAY = 0.5


async def search_track(artist: str, title: str) -> list[DeezerTrack]:
    query = f'artist:"{artist}" track:"{title}"'
    params: dict[str, str | int] = {"q": query, "limit": 20}

    async with _SEMAPHORE:
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(_DEEZER_SEARCH_URL, params=params)
                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("Retry-After", "1"))
                        await asyncio.sleep(retry_after + random.uniform(0, 0.5))
                        continue
                    resp.raise_for_status()
                    data = resp.json()

                results = []
                for item in data.get("data", []):
                    results.append(
                        DeezerTrack(
                            id=item["id"],
                            title=item["title"],
                            artist_name=item["artist"]["name"],
                            preview_url=item.get("preview", ""),
                            duration=item.get("duration", 0),
                            rank=item.get("rank", 0),
                        )
                    )
                return results

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BASE_DELAY * (2**attempt) + random.uniform(0, 0.2))
                    continue
                raise
            except Exception:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BASE_DELAY * (2**attempt) + random.uniform(0, 0.2))
                    continue
                raise

    return []


def _artist_matches(expected: str, found: str) -> bool:
    exp = expected.lower().strip()
    fnd = found.lower().strip()
    return exp in fnd or fnd in exp


def _select_best_match(expected_artist: str, candidates: list[DeezerTrack]) -> DeezerTrack | None:
    valid = [c for c in candidates if _artist_matches(expected_artist, c.artist_name)]
    if not valid:
        return None
    return max(valid, key=lambda t: t.rank)


async def match_spotify_to_deezer(spotify_tracks: list[SpotifyTrack]) -> list[PlayableTrack]:
    tasks = [search_track(st.artist, st.name) for st in spotify_tracks]
    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    playable: list[PlayableTrack] = []
    for st, results in zip(spotify_tracks, all_results, strict=False):
        if isinstance(results, Exception) or not results:
            continue
        best = _select_best_match(st.artist, results)  # type: ignore[arg-type]
        if best is None:
            continue
        if not best.preview_url:
            continue
        playable.append(
            PlayableTrack(
                name=st.name,
                artist=st.artist,
                preview_url=best.preview_url,
                duration_ms=best.duration * 1000,
                deezer_id=best.id,
            )
        )

    return playable