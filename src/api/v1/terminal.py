import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.iap import iap_ssh

router = APIRouter(tags=["terminal"])


@router.websocket("/ws/terminal")
async def terminal(ws: WebSocket):
    """Bidirectional interactive terminal: bridges WebSocket ↔ SSH shell on the VM.

    Client → Server:
        {"type": "data",   "data": "<keystrokes>"}
        {"type": "resize", "cols": 120, "rows": 40}

    Server → Client:
        {"type": "data",  "data": "<terminal output>"}
        {"type": "exit",  "code": <exit status>}
        {"type": "error", "detail": "<message>"}
    """
    await ws.accept()

    try:
        async with iap_ssh() as conn:
            async with conn.create_process(term_type="xterm-256color", term_size=(80, 24)) as proc:

                async def ws_to_ssh() -> None:
                    try:
                        async for msg in ws.iter_text():
                            try:
                                payload = json.loads(msg)
                                if payload.get("type") == "resize":
                                    proc.change_terminal_size(payload["cols"], payload["rows"])
                                elif payload.get("type") == "data":
                                    proc.stdin.write(payload["data"])
                            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                                # fall back to treating the raw message as terminal input
                                proc.stdin.write(msg)
                    except WebSocketDisconnect:
                        pass

                async def ssh_to_ws() -> None:
                    async for data in proc.stdout:
                        await ws.send_json({"type": "data", "data": data})
                    code = proc.exit_status if proc.exit_status is not None else -1
                    with contextlib.suppress(Exception):
                        await ws.send_json({"type": "exit", "code": code})
                        await ws.close()

                t_in = asyncio.create_task(ws_to_ssh())
                t_out = asyncio.create_task(ssh_to_ws())

                # Stop both sides as soon as either finishes (disconnect or shell exit).
                done, pending = await asyncio.wait(
                    [t_in, t_out], return_when=asyncio.FIRST_COMPLETED
                )
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                # Retrieve exceptions from finished tasks to silence
                # "Task exception was never retrieved" warnings.
                for t in done:
                    with contextlib.suppress(Exception):
                        t.result()

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        with contextlib.suppress(Exception):
            await ws.send_json({"type": "error", "detail": str(exc)})
