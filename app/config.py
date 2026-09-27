import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:  # noqa: ANN101
        self.spotify_client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
        self.spotify_client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        self.spotify_redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "")
        self.session_secret = os.getenv("SESSION_SECRET", "")
        # Production default: secure cookies
        self.cookie_secure = os.getenv("COOKIE_SECURE", "true").lower() == "true"
        # Level for the app's own diagnostic loggers (deezer/spotify/game
        # matching, request tracing). Default INFO to avoid noisy DEBUG logs
        # in production; set to DEBUG locally when investigating an issue.
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()