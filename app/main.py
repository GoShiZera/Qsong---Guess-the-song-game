from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.game_state import deserialize_session
from app.routes import auth, game

app = FastAPI()
app.add_middleware(HTTPSRedirectMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(Path("static/index.html"))


@app.middleware("http")
async def session_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    cookie = request.cookies.get("session")
    request.state.session = deserialize_session(cookie) if cookie else {}
    response = await call_next(request)
    return response


app.include_router(auth.router)
app.include_router(game.router)