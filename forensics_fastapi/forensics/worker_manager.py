"""
Core logic for Cloudflare Workers container control.

This module provides the CloudflareWorkerAPI client and WorkerLogStreamer helper.
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException

# ============================================================================
# Cloudflare Workers API Client
# ============================================================================

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareWorkerAPI:
    """
    Client for Cloudflare Workers REST API.

    Handles authentication and all lifecycle operations.
    """

    def __init__(
        self, api_token: str, account_id: str, script_name: str, base_url: str = CLOUDFLARE_API_BASE
    ):
        self.api_token = api_token
        self.account_id = account_id
        self.script_name = script_name
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make authenticated HTTP request to Cloudflare API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., /accounts/{id}/workers/scripts/{name})
            **kwargs: Additional arguments for httpx

        Returns:
            Parsed JSON response

        Raises:
            HTTPException on API errors
        """
        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(
                    method=method, url=url, headers=self.headers, **kwargs
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                error_detail = e.response.text
                try:
                    error_detail = e.response.json()
                except Exception:
                    pass
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Cloudflare API error: {error_detail}",
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")

    async def get_script_status(self) -> Dict[str, Any]:
        """
        Get script deployment status and metadata.

        Returns script info if exists, raises 404 if not deployed.
        """
        endpoint = f"/accounts/{self.account_id}/workers/scripts/{self.script_name}"
        return await self._request("GET", endpoint)

    async def list_scripts(self) -> Dict[str, Any]:
        """List all deployed scripts in account"""
        endpoint = f"/accounts/{self.account_id}/workers/scripts"
        return await self._request("GET", endpoint)

    async def deploy_script(
        self, code: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Deploy or redeploy a Worker script using the project's build command.

        Args:
            code: Ignored (deployment is handle by pnpm run deploy)
            metadata: Ignored

        Returns:
            Deployment response (mocked to match API structure)
        """
        cwd = os.getenv("PROJECT_ROOT", os.getcwd())
        # Use PROJECT_ROOT if set, otherwise current directory
        # cwd is already set above
        pass

        try:
            # Run 'pnpm run deploy' using asyncio subprocess
            process = await asyncio.create_subprocess_exec(
                "bun",
                "run",
                "deploy",
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else stdout.decode()
                raise HTTPException(
                    status_code=500,
                    detail=f"Deployment failed (exit code {process.returncode}): {error_msg}",
                )

            return {
                "success": True,
                "result": {
                    "id": self.script_name,
                    "tag": "latest",
                    "logs": stdout.decode(),  # custom field to see logs
                },
                "messages": [],
                "errors": [],
            }

        except FileNotFoundError:
            raise HTTPException(
                status_code=500, detail="Deployment tool 'bun' not found. Ensure it is in the PATH."
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Deployment execution failed: {str(e)}")

    async def delete_script(self) -> bool:
        """
        Delete/remove a Worker script.

        This effectively "powers off" the Worker.
        """
        endpoint = f"/accounts/{self.account_id}/workers/scripts/{self.script_name}"
        response = await self._request("DELETE", endpoint)
        return response.get("success", False)


# ============================================================================
# Log Streaming Helper
# ============================================================================


class WorkerLogStreamer:
    """
    Helper to stream Worker logs using wrangler tail.

    Falls back to recent logs if wrangler is unavailable.
    """

    def __init__(self, script_name: str, lines: int = 50):
        self.script_name = script_name
        self.lines = lines

    async def get_logs(self) -> List[Dict[str, Any]]:
        """
        Attempt to fetch recent logs.

        Returns:
            List of log entries (JSON objects from wrangler tail)
        """
        logs = []

        try:
            # Try to run wrangler tail with timeout
            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "bun",
                    "x",
                    "wrangler",
                    "tail",
                    self.script_name,
                    "--format",
                    "json",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=5.0,  # Short timeout to capture recent logs
            )

            # This will timeout, but we capture partial output
            stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=2.0)

            if stdout:
                for line in stdout.decode().strip().split("\n"):
                    if line.strip():
                        try:
                            log_entry = json.loads(line)
                            logs.append(log_entry)
                            if len(logs) >= self.lines:
                                break
                        except json.JSONDecodeError:
                            logs.append({"raw": line, "type": "text"})

        except (FileNotFoundError, asyncio.TimeoutError, Exception) as e:
            # wrangler not available or timed out
            # Return fallback: use API to get script status
            logs.append(
                {"type": "info", "message": f"Live logs unavailable: {str(e)}", "fallback": True}
            )

        return logs
