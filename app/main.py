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
from app.routes import auth, daily, game

# Configure logging for Render/Cloud deployment. The root level stays at
# INFO regardless of LOG_LEVEL to keep third-party library logs quiet; only
# this app's own diagnostic loggers (matching, token refresh, request
# tracing) follow LOG_LEVEL, which defaults to INFO and can be raised to
# DEBUG via the environment when investigating an issue.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)

_app_log_level = getattr(logging, settings.log_level, logging.INFO)
for _logger_name in ("app.services.deezer", "app.services.spotify", "app.routes.game"):
    logging.getLogger(_logger_name).setLevel(_app_log_level)


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


@app.get("/playlists")
async def playlists_page() -> FileResponse:
    return FileResponse(Path("static/index.html"))


# Browsers and link unfurlers request /favicon.ico at the root regardless of
# the <link rel="icon"> tags; serve the generated .ico instead of a 404.
@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(Path("static/favicon.ico"), media_type="image/x-icon")


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
app.include_router(daily.router)
