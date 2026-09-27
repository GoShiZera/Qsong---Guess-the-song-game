import asyncio
import logging
import random
import re
from difflib import SequenceMatcher

import httpx

from app.models import DeezerTrack, PlayableTrack, SpotifyTrack

_DEEZER_SEARCH_URL = "https://api.deezer.com/search"
_DEEZER_GLOBAL_CHART_URL = "https://api.deezer.com/chart/0/tracks"
_SEMAPHORE = asyncio.Semaphore(10)
_MAX_RETRIES = 3
_BASE_DELAY = 0.5

logger = logging.getLogger(__name__)


def _has_valid_preview(url: str | None) -> bool:
    return bool(url and url.strip())


async def search_track(artist: str, title: str) -> list[DeezerTrack]:
    # Deezer's search API doesn't support artist:"..." syntax (returns 0 results).
    # Use free text search which handles accents/special characters correctly.
    # We filter by artist match and rank in _select_best_match.
    query = f"{artist} {title}"
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
                    # Extract album image URL
                    album = item.get("album", {})
                    image_url = (
                        album.get("cover_medium")
                        or album.get("cover_big")
                        or album.get("cover")
                    )
                    results.append(
                        DeezerTrack(
                            id=item["id"],
                            title=item["title"],
                            artist_name=item["artist"]["name"],
                            preview_url=item.get("preview", ""),
                            duration=item.get("duration", 0),
                            rank=item.get("rank", 0),
                            image_url=image_url,
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


async def fetch_global_chart(limit: int = 50) -> list[PlayableTrack]:
    """Fetch Deezer's global top-tracks chart as playable tracks.

    Uses `title_short` (no "(feat. X)"/version suffix) as the name to guess,
    and drops any track without a preview.
    """
    params: dict[str, str | int] = {"limit": limit}
    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(_DEEZER_GLOBAL_CHART_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            break
        except httpx.HTTPError:
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_BASE_DELAY * (2**attempt) + random.uniform(0, 0.2))
                continue
            raise

    tracks: list[PlayableTrack] = []
    for item in data.get("data", []):
        preview = item.get("preview", "")
        if not _has_valid_preview(preview):
            continue
        album = item.get("album", {})
        tracks.append(
            PlayableTrack(
                name=item.get("title_short") or item["title"],
                artist=item["artist"]["name"],
                preview_url=preview,
                duration_ms=item.get("duration", 0) * 1000,
                deezer_id=item["id"],
                image_url=album.get("cover_medium") or album.get("cover"),
            )
        )
    logger.info("fetch_global_chart: %d playable tracks", len(tracks))
    return tracks


def _normalize_artist(name: str) -> str:
    """Normalize artist name for fuzzy matching.
    Handles common variations: 'e' <-> '&', removes extra spaces, etc.
    """
    normalized = name.lower().strip()
    # Normalize "e" <-> "&" (common in Portuguese duo names)
    normalized = normalized.replace(" & ", " e ").replace(" &", " e").replace("& ", "e ")
    # Also handle "feat.", "ft.", "part." variations
    normalized = normalized.replace(" feat. ", " ").replace(" ft. ", " ").replace(" part. ", " ")
    # Collapse multiple spaces
    while "  " in normalized:
        normalized = normalized.replace("  ", " ")
    return normalized.strip()


def _artist_matches(expected: str, found: str) -> bool:
    exp = _normalize_artist(expected)
    fnd = _normalize_artist(found)
    return exp in fnd or fnd in exp


# Parenthetical/suffix noise commonly found on Deezer titles that doesn't
# affect whether it's "the same song" (remaster tags, live/version notes).
_TITLE_NOISE_RE = re.compile(
    r"[\(\[][^)\]]*\b("
    r"remaster(ed)?|live|ao vivo|version|edit|mix|deluxe|bonus|anniversary|mono|stereo"
    r"|feat\.?|ft\.?|featuring"
    r")\b[^)\]]*[\)\]]",
    re.IGNORECASE,
)
_TITLE_TRAILING_TAG_RE = re.compile(
    r"\s*-\s*(live|remaster(ed)?|remix|acoustic|ao vivo|version|mono|stereo).*$",
    re.IGNORECASE,
)
_TITLE_FEAT_RE = re.compile(r"\s*(feat\.?|ft\.?|featuring)\s+.*$", re.IGNORECASE)


def _normalize_title(title: str) -> str:
    """Normalize a track title for fuzzy comparison, stripping noise like
    '(Remastered 2011)', '- Live', 'feat. X', etc. that Deezer/Spotify
    titles frequently disagree on despite being the same song."""
    normalized = title.lower().strip()
    normalized = _TITLE_NOISE_RE.sub(" ", normalized)
    normalized = _TITLE_TRAILING_TAG_RE.sub("", normalized)
    normalized = _TITLE_FEAT_RE.sub("", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _title_matches(expected: str, found: str, threshold: float = 0.6) -> bool:
    """Check the candidate is plausibly the *same song*, not just the same
    artist. Without this, matching by artist + Deezer rank alone can pick a
    completely different (more popular) track by the same artist."""
    exp = _normalize_title(expected)
    fnd = _normalize_title(found)
    if not exp or not fnd:
        return False
    if exp == fnd:
        return True
    shorter, longer = (exp, fnd) if len(exp) <= len(fnd) else (fnd, exp)
    # A one-sided containment only counts as a match if the shorter title
    # makes up a substantial share of the longer one — otherwise short/generic
    # titles ("Song") would match almost anything ("A Totally Different Song").
    if shorter in longer and len(shorter) / len(longer) >= 0.5:
        return True
    return SequenceMatcher(None, exp, fnd).ratio() >= threshold


def _select_best_match(
    expected_artist: str, expected_title: str, candidates: list[DeezerTrack]
) -> DeezerTrack | None:
    valid = [
        c
        for c in candidates
        if _artist_matches(expected_artist, c.artist_name)
        and _title_matches(expected_title, c.title)
    ]
    if not valid:
        return None
    return max(valid, key=lambda t: t.rank)


async def match_spotify_to_deezer(spotify_tracks: list[SpotifyTrack]) -> list[PlayableTrack]:
    """
    Match Spotify tracks to playable tracks.
    Priority: 1) Spotify preview_url, 2) Deezer search, 3) Skip if no preview found.
    """
    logger.info("match_spotify_to_deezer: received %d Spotify tracks", len(spotify_tracks))
    
    # First, separate tracks that already have Spotify preview
    def _has_spotify_preview(st: SpotifyTrack) -> bool:
        return _has_valid_preview(st.preview_url)

    tracks_with_spotify_preview = [st for st in spotify_tracks if _has_spotify_preview(st)]
    tracks_without_preview = [st for st in spotify_tracks if not _has_spotify_preview(st)]

    logger.info(
        "match_spotify_to_deezer: %d tracks with Spotify preview, %d without",
        len(tracks_with_spotify_preview),
        len(tracks_without_preview),
    )

    # Log tracks with Spotify preview
    for i, st in enumerate(tracks_with_spotify_preview):
        logger.debug(
            "Track %d/%d (Spotify preview): %s - %s | preview_url=%s | duration_ms=%d",
            i + 1,
            len(tracks_with_spotify_preview),
            st.artist,
            st.name,
            (st.preview_url[:80] + "..." if st.preview_url and len(st.preview_url) > 80
             else st.preview_url),
            st.duration_ms,
        )

    playable: list[PlayableTrack] = []

    # 1. Use Spotify preview directly for tracks that have it
    # Use negative IDs to distinguish Spotify-sourced tracks
    # (avoid collision with Deezer IDs which are positive)
    spotify_id_counter = -1
    for st in tracks_with_spotify_preview:
        playable.append(
            PlayableTrack(
                name=st.name,
                artist=st.artist,
                preview_url=st.preview_url or "",
                duration_ms=st.duration_ms,
                deezer_id=spotify_id_counter,
                image_url=st.image_url,
            )
        )
        spotify_id_counter -= 1

    # 2. For tracks without Spotify preview, search Deezer
    if tracks_without_preview:
        logger.info(
            "match_spotify_to_deezer: searching Deezer for %d tracks",
            len(tracks_without_preview),
        )
        tasks = [search_track(st.artist, st.name) for st in tracks_without_preview]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        deezer_success = 0
        deezer_no_results = 0
        deezer_no_artist_match = 0
        deezer_no_preview = 0
        deezer_errors = 0

        for i, (st, results) in enumerate(zip(tracks_without_preview, all_results, strict=False)):
            if isinstance(results, Exception):
                logger.warning(
                    "Deezer search failed for %s - %s: %s",
                    st.artist,
                    st.name,
                    results,
                )
                deezer_errors += 1
                continue
            # Type narrowing: results is list[DeezerTrack] here
            deezer_results: list[DeezerTrack] = results  # type: ignore[assignment]
            if not deezer_results:
                logger.debug(
                    "Deezer search [%d/%d]: no results for '%s - %s'",
                    i + 1,
                    len(tracks_without_preview),
                    st.artist,
                    st.name,
                )
                deezer_no_results += 1
                continue

            logger.debug(
                "Deezer search [%d/%d]: found %d results for '%s - %s'",
                i + 1,
                len(tracks_without_preview),
                len(deezer_results),
                st.artist,
                st.name,
            )

            best = _select_best_match(st.artist, st.name, deezer_results)
            if best is None:
                logger.debug(
                    "Deezer search [%d/%d]: no artist/title match for '%s - %s' "
                    "(found: %s)",
                    i + 1,
                    len(tracks_without_preview),
                    st.artist,
                    st.name,
                    [f"{r.artist_name} - {r.title}" for r in deezer_results[:5]],
                )
                deezer_no_artist_match += 1
                continue
            if not _has_valid_preview(best.preview_url):
                logger.debug(
                    (
            "Deezer search [%d/%d]: artist match found but NO PREVIEW "
            "for '%s - %s' (matched: %s - %s)",
        ),
                    i + 1,
                    len(tracks_without_preview),
                    st.artist,
                    st.name,
                    best.artist_name,
                    best.title,
                )
                deezer_no_preview += 1
                continue
            # Use Spotify track image if available, otherwise Deezer match image
            image_url = st.image_url or best.image_url
            playable.append(
                PlayableTrack(
                    name=st.name,
                    artist=st.artist,
                    preview_url=best.preview_url,
                    duration_ms=best.duration * 1000,
                    deezer_id=best.id,
                    image_url=image_url,
                )
            )
            deezer_success += 1
            logger.debug(
                (
            "Deezer search [%d/%d]: SUCCESS - '%s - %s' -> Deezer match "
            "'%s - %s' (preview: %s)",
        ),
                i + 1,
                len(tracks_without_preview),
                st.artist,
                st.name,
                best.artist_name,
                best.title,
                (
                best.preview_url[:80] + "..."
                if best.preview_url and len(best.preview_url) > 80
                else best.preview_url
            ),
            )

        logger.info(
            (
            "match_spotify_to_deezer: Deezer results - success: %d, "
            "no_results: %d, no_artist_match: %d, no_preview: %d, errors: %d",
        ),
            deezer_success,
            deezer_no_results,
            deezer_no_artist_match,
            deezer_no_preview,
            deezer_errors,
        )

    logger.info(
        "match_spotify_to_deezer: returning %d playable tracks "
        "(Spotify: %d, Deezer: %d)",
        len(playable),
        len(tracks_with_spotify_preview),
        len(playable) - len(tracks_with_spotify_preview),
    )
    return playable