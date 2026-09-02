from fastapi import APIRouter

router = APIRouter()


@router.get("/login")
async def login() -> dict[str, str]:
    return {"message": "TODO: redirect to Spotify auth"}


@router.get("/callback")
async def callback() -> dict[str, str]:
    return {"message": "TODO: exchange code for tokens"}