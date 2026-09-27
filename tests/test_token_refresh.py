"""Regression tests for persisting a refreshed Spotify access token.

Without this, a token refreshed mid-request (e.g. inside `fetch_user_profile`)
was used only for that single request and then discarded, silently logging
the user out the next time the original access token expired.
"""

from http.cookies import SimpleCookie
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.game_state import deserialize_session, serialize_session
from app.main import app


async def _make_client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    )


def _cookie_session(access_token: str, refresh_token: str) -> str:
    return serialize_session(
        {
            "user_tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": 3600,
            },
            "authenticated": True,
        }
    )


@pytest.mark.asyncio
async def test_user_profile_persists_refreshed_token() -> None:
    cookie_value = _cookie_session("old-access", "old-refresh")

    async def fake_fetch_user_profile(
        access_token: str,
        refresh_token: str | None = None,
        token_update: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        assert access_token == "old-access"
        if token_update is not None:
            token_update["access_token"] = "new-access"
            token_update["refresh_token"] = "new-refresh"
        return {"id": "u1", "display_name": "Test User", "avatar_url": None}

    with patch("app.routes.game.fetch_user_profile", side_effect=fake_fetch_user_profile):
        async with await _make_client() as client:
            # A signed session cookie's value is raw JSON (spaces, quotes),
            # which needs RFC 6265 quoting — use the cookie jar (as a real
            # browser / response.set_cookie would) instead of a raw header.
            client.cookies.set("auth_session", cookie_value)
            resp = await client.get("/user/profile")

    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie")
    assert set_cookie is not None
    assert set_cookie.startswith("auth_session=")

    # response.set_cookie() quotes/escapes the raw JSON payload using Python's
    # http.cookies scheme (octal-escaped commas, backslash-escaped quotes);
    # unquote it the same way rather than a naive string split.
    jar = SimpleCookie()
    jar.load(set_cookie)
    new_cookie_value = jar["auth_session"].value
    restored = deserialize_session(new_cookie_value)
    assert restored is not None
    assert restored["user_tokens"]["access_token"] == "new-access"
    assert restored["user_tokens"]["refresh_token"] == "new-refresh"


@pytest.mark.asyncio
async def test_user_profile_does_not_set_cookie_when_token_unchanged() -> None:
    cookie_value = _cookie_session("valid-access", "valid-refresh")

    async def fake_fetch_user_profile(
        access_token: str,
        refresh_token: str | None = None,
        token_update: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del access_token, refresh_token, token_update  # unused: no refresh here
        return {"id": "u1", "display_name": "Test User", "avatar_url": None}

    with patch("app.routes.game.fetch_user_profile", side_effect=fake_fetch_user_profile):
        async with await _make_client() as client:
            client.cookies.set("auth_session", cookie_value)
            resp = await client.get("/user/profile")

    assert resp.status_code == 200
    assert resp.headers.get("set-cookie") is None
