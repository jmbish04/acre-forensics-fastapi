import asyncio
import os
import pty
import subprocess
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/ws", tags=["Terminal"])


@router.websocket("/terminal")
async def terminal_websocket(websocket: WebSocket, token: Optional[str] = Query(None)):
    """
    Establish a PTY (Pseudo-Terminal) session over WebSocket.
    """
    # 1. Security Check (Basic token validation if needed)
    # The WORKER_API_KEY is used for internal auth.
    container_secret = os.getenv("WORKER_API_KEY")
    if container_secret and token != container_secret:
        # Note: WebSocket.close() doesn't return a Response, so we just close with a code.
        await websocket.accept()  # We have to accept before we can close with code in some versions
        await websocket.send_json({"error": "Unauthorized: Invalid Session-Token"})
        await websocket.close(code=4003)
        return

    await websocket.accept()

    # 2. Setup PTY
    master_fd, slave_fd = pty.openpty()

    # Spawn shell (bash)
    # We use /bin/bash if available, fallback to /bin/sh
    shell = "/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh"

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["COLUMNS"] = "80"
    env["LINES"] = "24"

    process = subprocess.Popen(
        [shell],
        preexec_fn=os.setsid,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        universal_newlines=False,
        env=env,
    )

    # Close the slave side in the parent process
    os.close(slave_fd)

    # 3. Bi-directional data flow

    # Output reader (PTY -> WebSocket)
    async def pty_to_ws():
        loop = asyncio.get_event_loop()
        try:
            while True:
                # Use a thread pool for blocking os.read
                data = await loop.run_in_executor(None, os.read, master_fd, 4096)
                if not data:
                    break
                await websocket.send_bytes(data)
        except Exception as e:
            print(f"PTY Output Reader error: {e}")
        finally:
            if websocket.client_state.value != 3:  # 3 is DISCONNECTED
                await websocket.close()

    # Input writer (WebSocket -> PTY)
    async def ws_to_pty():
        try:
            while True:
                data = await websocket.receive_bytes()
                os.write(master_fd, data)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"PTY Input Writer error: {e}")
        finally:
            # Kill process if websocket closes
            if process.poll() is None:
                process.terminate()
            try:
                os.close(master_fd)
            except Exception:
                pass

    # Run both concurrently
    try:
        await asyncio.gather(pty_to_ws(), ws_to_pty())
    except Exception as e:
        print(f"Terminal session ended with error: {e}")
    finally:
        if process.poll() is None:
            process.terminate()
