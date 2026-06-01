import os
from dataclasses import dataclass


@dataclass
class Settings:
    claude_bin: str = os.getenv("CLAUDE_BIN", "claude")
    sync_timeout: float = float(os.getenv("SYNC_TIMEOUT", "120"))
    # GCP / IAP tunnel
    gcp_project: str = os.getenv("GCP_PROJECT", "")
    gcp_zone: str = os.getenv("GCP_ZONE", "")
    vm_name: str = os.getenv("VM_NAME", "")
    vm_user: str = os.getenv("VM_USER", "")
    ssh_key_ttl_minutes: int = int(os.getenv("SSH_KEY_TTL_MINUTES", "5"))


settings = Settings()

_REQUIRED = ["gcp_project", "gcp_zone", "vm_name", "vm_user"]
_missing = [k for k in _REQUIRED if not getattr(settings, k)]
if _missing:
    raise RuntimeError(f"Missing required env vars: {', '.join(v.upper() for v in _missing)}")
