import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..worker_manager import CloudflareWorkerAPI, WorkerLogStreamer

router = APIRouter(prefix="/api/container", tags=["Container Control"])

# Environment Variables
# (now read inside get_cloudflare_client)

# Default Worker code (used for deployment)
DEFAULT_WORKER_CODE = """
export default {
  async fetch(request, env, ctx) {
    return new Response("Acre Forensics Worker Active", { status: 200 });
  },
};
"""

# ============================================================================
# Models
# ============================================================================


class ContainerStatus(BaseModel):
    """Container/Worker status response"""

    name: str
    active: bool
    deployed_at: Optional[str] = None
    last_modified: Optional[str] = None
    status: str = Field(description="one of: active, inactive, error")
    metadata: Optional[Dict[str, Any]] = None


class ContainerLogs(BaseModel):
    """Recent logs from Worker"""

    worker_name: str
    logs: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: str
    count: int = 0


class PowerAction(BaseModel):
    """Response to power on/off actions"""

    worker_name: str
    action: str  # "on", "off", "restart"
    success: bool
    message: str
    deployment_time: Optional[str] = None


class RestartAction(BaseModel):
    """Restart response"""

    worker_name: str
    action: str = "restart"
    success: bool
    message: str
    previous_deployment: Optional[str] = None
    new_deployment: Optional[str] = None


# ============================================================================
# Dependency Injection
# ============================================================================


def get_cloudflare_client() -> CloudflareWorkerAPI:
    """Dependency injection for Cloudflare API client"""
    from ..cloudflare_ops import get_cloudflare_config

    # Read env/config using the router logic
    config = get_cloudflare_config()

    # WORKER_ADMIN_TOKEN is preferred for Worker management
    # But currently CloudflareWorkerAPI expects 'api_token' (generic)
    # We will pass the specific token as api_token
    api_token = config.get("workerAdminToken") or config.get("apiToken")
    account_id = config.get("accountId")
    script_name = config.get("workerScriptName") or ""

    if not api_token or not account_id:
        raise HTTPException(
            status_code=500,
            detail="Missing CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID environment variables",
        )
    return CloudflareWorkerAPI(api_token=api_token, account_id=account_id, script_name=script_name)


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/status", response_model=ContainerStatus, summary="Get Worker Status")
async def get_container_status(
    client: CloudflareWorkerAPI = Depends(get_cloudflare_client),
) -> ContainerStatus:
    """
    Get the status of the Worker.
    """
    try:
        response = await client.get_script_status()

        if response.get("success"):
            script = response.get("result", {})
            return ContainerStatus(
                name=client.script_name,
                active=True,
                deployed_at=script.get("created_on"),
                last_modified=script.get("modified_on"),
                status="active",
                metadata=script,
            )
    except HTTPException as e:
        if e.status_code == 404:
            return ContainerStatus(name=client.script_name, active=False, status="inactive")
        raise

    return ContainerStatus(name=client.script_name, active=False, status="error")


@router.get("/logs", response_model=ContainerLogs, summary="Get Worker Logs")
async def get_container_logs(
    client: CloudflareWorkerAPI = Depends(get_cloudflare_client),
) -> ContainerLogs:
    """
    Get recent logs from the Worker.
    """
    streamer = WorkerLogStreamer(client.script_name, lines=50)
    logs = await streamer.get_logs()

    return ContainerLogs(
        worker_name=client.script_name,
        logs=logs,
        timestamp=datetime.now(timezone.utc).isoformat(),
        count=len(logs),
    )


@router.post("/power/on", response_model=PowerAction, summary="Power On Worker")
async def power_on_container(
    client: CloudflareWorkerAPI = Depends(get_cloudflare_client),
) -> PowerAction:
    """
    Deploy/enable the Worker.
    """
    try:
        worker_code = DEFAULT_WORKER_CODE
        code_path = os.getenv("WORKER_CODE_PATH")
        if code_path and os.path.exists(code_path):
            with open(code_path, "r") as f:
                worker_code = f.read()

        response = await client.deploy_script(
            code=worker_code, metadata={"main_module": "index.js"}
        )

        if response.get("success"):
            return PowerAction(
                worker_name=client.script_name,
                action="on",
                success=True,
                message="Worker deployed successfully",
                deployment_time=datetime.now(timezone.utc).isoformat(),
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deploy Worker: {str(e)}")

    raise HTTPException(status_code=500, detail="Deployment failed")


@router.post("/power/off", response_model=PowerAction, summary="Power Off Worker")
async def power_off_container(
    client: CloudflareWorkerAPI = Depends(get_cloudflare_client),
) -> PowerAction:
    """
    Power off/disable the Worker.
    """
    try:
        success = await client.delete_script()

        if success:
            return PowerAction(
                worker_name=client.script_name,
                action="off",
                success=True,
                message="Worker deleted successfully",
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete Worker: {str(e)}")

    raise HTTPException(status_code=500, detail="Deletion failed")


@router.post("/restart", response_model=RestartAction, summary="Restart Worker")
async def restart_container(
    client: CloudflareWorkerAPI = Depends(get_cloudflare_client),
) -> RestartAction:
    """
    Restart the Worker.
    """
    try:
        # Get current deployment info
        current_status = await client.get_script_status()
        current_time = current_status.get("result", {}).get("modified_on")

        worker_code = DEFAULT_WORKER_CODE
        code_path = os.getenv("WORKER_CODE_PATH")
        if code_path and os.path.exists(code_path):
            with open(code_path, "r") as f:
                worker_code = f.read()

        response = await client.deploy_script(
            code=worker_code, metadata={"main_module": "index.js"}
        )

        if response.get("success"):
            new_time = response.get("result", {}).get("modified_on")
            return RestartAction(
                worker_name=client.script_name,
                action="restart",
                success=True,
                message="Worker redeployed and restarted",
                previous_deployment=current_time,
                new_deployment=new_time,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart Worker: {str(e)}")

    raise HTTPException(status_code=500, detail="Restart failed")
