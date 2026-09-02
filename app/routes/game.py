from fastapi import APIRouter

router = APIRouter()


@router.get("/playlists")
async def playlists() -> dict[str, str]:
    return {"message": "TODO: list playlists"}


@router.get("/playlist/{playlist_id}/tracks")
async def playlist_tracks(playlist_id: str) -> dict[str, str]:
    return {"message": f"TODO: get tracks for {playlist_id}"}


@router.post("/round/start")
async def round_start() -> dict[str, str]:
    return {"message": "TODO: start round"}


@router.post("/round/guess")
async def round_guess() -> dict[str, str]:
    return {"message": "TODO: process guess"}


@router.post("/round/skip")
async def round_skip() -> dict[str, str]:
    return {"message": "TODO: skip round"}