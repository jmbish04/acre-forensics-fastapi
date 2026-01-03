import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from forensics_fastapi.cli import execute_command, get_health_status, get_system_info, run_scan_logic

router = APIRouter()

@router.websocket("/ws/container/sandbox/cli/{method}")
async def ws_cli_endpoint(websocket: WebSocket, method: str):
    await websocket.accept()
    try:
        while True:
            # Wait for any input (optional args)
            # For simple methods like health/sysinfo, we might just run once and close,
            # or keep open for periodic updates.
            # The prompt implies "expose methods", usually request-response style over WS or stream.
            # Let's assume a simple protocol: optional JSON payload -> Result -> Close? 
            # Or keep open for multiple commands?
            # Let's read one message to trigger the action (if args needed) or valid immediate trigger.
            
            data = None
            try:
                # We expect a JSON payload for 'exec' or 'scan', maybe empty for others
                payload = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                if payload:
                    data = json.loads(payload)
            except asyncio.TimeoutError:
                pass # No input, proceed with defaults if allowed
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON payload"})
                continue
            
            if method == "health":
                result = get_health_status()
                await websocket.send_json({"type": "health", "data": result})
                # For health, maybe we just return one snapshot?
            
            elif method == "sysinfo":
                result = get_system_info()
                await websocket.send_json({"type": "sysinfo", "data": result})
            
            elif method == "exec":
                cmd = data.get("cmd") if data else None
                if not cmd:
                    await websocket.send_json({"error": "Missing 'cmd' in payload for exec"})
                else:
                    await websocket.send_json({"type": "exec_start", "cmd": cmd})
                    result = execute_command(cmd)
                    await websocket.send_json({"type": "exec_result", "data": result})
            
            elif method == "scan":
                target = data.get("target", "all") if data else "all"
                auto_fix = data.get("auto_fix", False) if data else False
                
                await websocket.send_json({"type": "scan_start", "target": target})
                try:
                    # run_scan_logic is async
                    await run_scan_logic(target, auto_fix)
                    await websocket.send_json({"type": "scan_complete", "status": "success"})
                except Exception as e:
                     await websocket.send_json({"type": "scan_error", "error": str(e)})

            else:
                 await websocket.send_json({"error": f"Unknown method: {method}"})

            # For now, let's wait for next command or just close? 
            # The user might want to keep the socket open.
            # We'll just loop.
            payload = await websocket.receive_text() # Block for next request or close
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        # Try to send error if possible
        try:
            await websocket.send_json({"error": "Internal Error", "details": str(e)})
        except Exception:
            pass
