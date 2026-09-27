import logging
import sys
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.config import settings
from app.game_state import deserialize_session
from app.routes import auth, game

# Configure logging for Render/Cloud deployment
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)

# Set specific loggers to DEBUG for detailed tracking
logging.getLogger("app.services.deezer").setLevel(logging.DEBUG)
logging.getLogger("app.services.spotify").setLevel(logging.DEBUG)
logging.getLogger("app.routes.game").setLevel(logging.DEBUG)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    # Fail fast instead of silently signing every session cookie with an
    # empty key. This only runs when the app is actually served (uvicorn,
    # the Render process) — tests talk to the app via httpx.ASGITransport,
    # which never triggers ASGI lifespan events, so this doesn't affect them.
    if settings.cookie_secure and not settings.session_secret:
        raise RuntimeError(
            "SESSION_SECRET não pode estar vazio quando COOKIE_SECURE=true "
            "(produção). Defina a variável de ambiente SESSION_SECRET antes "
            "de iniciar o servidor."
        )
    yield


app = FastAPI(lifespan=lifespan)
if settings.cookie_secure:
    app.add_middleware(HTTPSRedirectMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(Path("static/index.html"))


@app.get("/select-playlist")
async def select_playlist_page() -> FileResponse:
    return FileResponse(Path("static/index.html"))


@app.middleware("http")
async def session_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    cookie = request.cookies.get("auth_session")
    request.state.session = deserialize_session(cookie) if cookie else {}
    response = await call_next(request)
    return response


app.include_router(auth.router)
app.include_router(game.router)
