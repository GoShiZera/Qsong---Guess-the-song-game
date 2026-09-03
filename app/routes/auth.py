import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.config import settings
from app.game_state import serialize_session
from app.services.spotify import exchange_code_for_tokens, get_auth_url

router = APIRouter()


@router.get("/login")
async def login(request: Request, response: Response) -> RedirectResponse:
    state = secrets.token_urlsafe(16)
    response.set_cookie(
        key="oauth_state",
        value=state,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    auth_url = get_auth_url(state)
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"Spotify auth error: {error}")

    stored_state = request.cookies.get("oauth_state")
    if not stored_state or state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        token_data = await exchange_code_for_tokens(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to exchange code: {e}") from None

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)

    session_data = {
        "user_tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
        },
        "authenticated": True,
    }

    cookie = serialize_session(session_data)
    response = RedirectResponse(url="/select-playlist")
    response.set_cookie(
        key="session",
        value=cookie,
        max_age=60 * 60 * 24 * 7,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.delete_cookie("oauth_state")
    return response


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie("session")
    return {"message": "Logged out"}