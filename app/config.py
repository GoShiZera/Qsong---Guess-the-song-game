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


settings = Settings()