import os
from dataclasses import dataclass


@dataclass
class Settings:
    claude_bin: str = os.getenv("CLAUDE_BIN", "claude")
    sync_timeout: float = float(os.getenv("SYNC_TIMEOUT", "120"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")


settings = Settings()
