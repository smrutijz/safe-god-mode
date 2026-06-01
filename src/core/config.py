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
    iap_local_port: int = int(os.getenv("IAP_LOCAL_PORT", "2222"))


settings = Settings()
