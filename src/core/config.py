import os
from dataclasses import dataclass
from typing import Optional


def _str(key: str) -> Optional[str]:
    val = os.getenv(key)
    return val if val else None


def _float(key: str) -> Optional[float]:
    val = os.getenv(key)
    return float(val) if val else None


def _int(key: str) -> Optional[int]:
    val = os.getenv(key)
    return int(val) if val else None


@dataclass
class Settings:
    # GCP / IAP tunnel
    gcp_project: Optional[str] = _str("GCP_PROJECT")
    gcp_zone: Optional[str] = _str("GCP_ZONE")
    vm_name: Optional[str] = _str("VM_NAME")
    vm_user: Optional[str] = _str("VM_USER")
    # Claude
    claude_bin: Optional[str] = _str("CLAUDE_BIN")
    # Timeouts / TTL — defaults live in .env.example, not here
    sync_timeout_seconds: Optional[float] = _float("SYNC_TIMEOUT_SECONDS")
    iap_tunnel_timeout_seconds: Optional[float] = _float("IAP_TUNNEL_TIMEOUT_SECONDS")
    ssh_key_ttl_minutes: Optional[int] = _int("SSH_KEY_TTL_MINUTES")


settings = Settings()

_REQUIRED = [
    "gcp_project",
    "gcp_zone",
    "vm_name",
    "vm_user",
    "claude_bin",
    "sync_timeout_seconds",
    "iap_tunnel_timeout_seconds",
    "ssh_key_ttl_minutes",
]
_missing = [k for k in _REQUIRED if getattr(settings, k) is None]
if _missing:
    raise RuntimeError(f"Missing required env vars: {', '.join(v.upper() for v in _missing)}")
