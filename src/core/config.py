import os
from dataclasses import dataclass


@dataclass
class Settings:
    claude_bin: str = os.getenv("CLAUDE_BIN", "claude")
    # max seconds the SYNC /execute endpoint will wait before killing the run
    sync_timeout: float = float(os.getenv("SYNC_TIMEOUT", "120"))


settings = Settings()
