import os
import tempfile

from _pytest.monkeypatch import MonkeyPatch

from app.config import Settings


def test_settings_loads_from_env(monkeypatch: MonkeyPatch) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("SPOTIFY_CLIENT_ID=test_id\n")
        f.write("SPOTIFY_CLIENT_SECRET=test_secret\n")
        f.write("SPOTIFY_REDIRECT_URI=http://localhost:8000/callback\n")
        f.write("SESSION_SECRET=test_secret_key_32_chars_long!!\n")
        env_path = f.name

    try:
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test_id")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("SPOTIFY_REDIRECT_URI", "http://localhost:8000/callback")
        monkeypatch.setenv("SESSION_SECRET", "test_secret_key_32_chars_long!!")

        s = Settings()
        assert s.spotify_client_id == "test_id"
        assert s.spotify_client_secret == "test_secret"
        assert s.spotify_redirect_uri == "http://localhost:8000/callback"
        assert s.session_secret == "test_secret_key_32_chars_long!!"
    finally:
        os.unlink(env_path)