import asyncio
import contextlib

import asyncssh

from src.core.config import settings


async def _wait_tunnel_ready(stderr, timeout: float = 15.0) -> None:
    """Read gcloud stderr until it signals the tunnel is listening."""
    async def _read():
        async for line in stderr:
            if b"Listening on port" in line:
                return
        raise RuntimeError("gcloud tunnel exited before becoming ready")

    try:
        await asyncio.wait_for(_read(), timeout=timeout)
    except asyncio.TimeoutError:
        raise RuntimeError("Timed out waiting for IAP tunnel to become ready")


@contextlib.asynccontextmanager
async def iap_ssh():
    """Async context manager: opens an IAP tunnel then yields an asyncssh connection.

    Usage:
        async with iap_ssh() as conn:
            result = await conn.run("claude -p ...")
    """
    proc = await asyncio.create_subprocess_exec(
        "gcloud", "compute", "start-iap-tunnel",
        settings.vm_name, "22",
        f"--local-host-port=localhost:{settings.iap_local_port}",
        f"--zone={settings.gcp_zone}",
        f"--project={settings.gcp_project}",
        "--quiet",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        await _wait_tunnel_ready(proc.stderr)
    except RuntimeError:
        proc.terminate()
        await proc.wait()
        raise

    try:
        async with asyncssh.connect(
            "localhost",
            port=settings.iap_local_port,
            username=settings.vm_user,
            known_hosts=None,  # dynamic tunnel — no stable host key to verify
        ) as conn:
            yield conn
    finally:
        proc.terminate()
        await proc.wait()
