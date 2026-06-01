import asyncio
import contextlib
import socket
from datetime import datetime, timedelta, timezone
import asyncssh
from google.api_core import exceptions as gcp_exceptions
from google.cloud import compute_v1
from src.core.config import settings


_metadata_lock = asyncio.Lock()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


async def _drain(stream) -> None:
    try:
        async for _ in stream:
            pass
    except Exception:
        pass


async def _wait_tunnel_ready(stderr, timeout: float = None) -> None:
    async def _read():
        async for line in stderr:
            if b"Listening on port" in line:
                return
        raise RuntimeError("gcloud tunnel exited before becoming ready")

    resolved_timeout = timeout if timeout is not None else settings.iap_tunnel_timeout_seconds
    try:
        await asyncio.wait_for(_read(), timeout=resolved_timeout)
    except asyncio.TimeoutError:
        raise RuntimeError("Timed out waiting for IAP tunnel to become ready")

    asyncio.create_task(_drain(stderr))


def _key_entry(pubkey_str: str) -> str:
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=settings.ssh_key_ttl_minutes)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    return (
        f'{settings.vm_user}:{pubkey_str} google-ssh '
        f'{{"userName":"{settings.vm_user}@managed","expireOn":"{expiry}"}}'
    )


def _sync_update_metadata(add_line: str = None, remove_line: str = None) -> None:
    """Read-modify-write ssh-keys instance metadata with fingerprint-based retry."""
    client = compute_v1.InstancesClient()
    for _ in range(5):
        instance = client.get(
            project=settings.gcp_project,
            zone=settings.gcp_zone,
            instance=settings.vm_name,
        )
        meta = instance.metadata
        items = list(meta.items) if meta.items else []
        ssh_item = next((i for i in items if i.key == "ssh-keys"), None)
        lines = ssh_item.value.splitlines() if ssh_item else []

        if add_line:
            lines.append(add_line)
        if remove_line:
            lines = [l for l in lines if remove_line not in l]

        new_items = [i for i in items if i.key != "ssh-keys"]
        if lines:
            new_items.append(compute_v1.Items(key="ssh-keys", value="\n".join(lines)))

        try:
            op = client.set_metadata(
                project=settings.gcp_project,
                zone=settings.gcp_zone,
                instance=settings.vm_name,
                metadata_resource=compute_v1.Metadata(
                    fingerprint=meta.fingerprint,
                    items=new_items,
                ),
            )
            op.result()  # blocks until the GCP operation completes
            return
        except gcp_exceptions.Aborted:
            continue  # fingerprint conflict — another request modified metadata, retry

    raise RuntimeError("Failed to update VM SSH key metadata after 5 retries")


async def _inject_key(entry: str) -> None:
    async with _metadata_lock:
        await asyncio.to_thread(_sync_update_metadata, add_line=entry)


async def _remove_key(entry: str) -> None:
    async with _metadata_lock:
        await asyncio.to_thread(_sync_update_metadata, remove_line=entry)


async def _ssh_connect(local_port: int, private_key, retries: int = 8):
    """Retry SSH connect to handle GCP metadata propagation lag (~1-5s)."""
    for attempt in range(retries):
        try:
            return await asyncssh.connect(
                "localhost",
                port=local_port,
                username=settings.vm_user,
                client_keys=[private_key],
                known_hosts=None,
            )
        except (asyncssh.PermissionDenied, asyncssh.DisconnectError):
            if attempt < retries - 1:
                await asyncio.sleep(1)
            else:
                raise RuntimeError(
                    f"SSH auth failed after {retries}s — ephemeral key not propagated to VM"
                )


@contextlib.asynccontextmanager
async def iap_ssh():
    """Open an IAP tunnel + SSH connection backed by a per-request ephemeral ED25519 key.

    Key is injected into GCP instance metadata on entry (5-min GCP expiry) and
    explicitly removed on exit. Tunnel start and key injection run in parallel.
    """
    local_port = _free_port()
    private_key = asyncssh.generate_private_key("ssh-ed25519")
    pubkey_str = private_key.export_public_key("openssh").decode().strip()
    entry = _key_entry(pubkey_str)

    proc = await asyncio.create_subprocess_exec(
        "gcloud", "compute", "start-iap-tunnel",
        settings.vm_name, "22",
        f"--local-host-port=localhost:{local_port}",
        f"--zone={settings.gcp_zone}",
        f"--project={settings.gcp_project}",
        "--quiet",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    inject_task = asyncio.create_task(_inject_key(entry))
    tunnel_task = asyncio.create_task(_wait_tunnel_ready(proc.stderr))

    try:
        # Inject the key and wait for the tunnel to be ready in parallel.
        await asyncio.gather(inject_task, tunnel_task)
    except Exception:
        # Cancel whichever task is still running and drain both so their
        # exceptions are retrieved (prevents "Task exception was never retrieved").
        for t in (inject_task, tunnel_task):
            t.cancel()
        await asyncio.gather(inject_task, tunnel_task, return_exceptions=True)
        proc.terminate()
        await proc.wait()
        with contextlib.suppress(Exception):
            await _remove_key(entry)
        raise

    try:
        conn = await _ssh_connect(local_port, private_key)
        async with conn:
            yield conn
    finally:
        proc.terminate()
        await proc.wait()
        with contextlib.suppress(Exception):
            await _remove_key(entry)
