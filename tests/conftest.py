from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def no_preview_refresh() -> Iterator[AsyncMock]:
    """round_start refreshes Deezer preview URLs over the network; keep tests
    offline by default (None = keep the stored URL). Tests that care about the
    refresh can configure the yielded mock."""
    mock = AsyncMock(return_value=None)
    with patch("app.routes.game.fetch_fresh_preview", mock):
        yield mock
