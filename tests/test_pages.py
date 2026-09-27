import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/", "/playlists", "/select-playlist"])
async def test_spa_routes_serve_index(path: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as client:
        resp = await client.get(path)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert 'id="view-home"' in resp.text
