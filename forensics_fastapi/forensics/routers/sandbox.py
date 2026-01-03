import os
import subprocess
from typing import Dict

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

router = APIRouter(tags=["Sandbox"])

class ExecRequest(BaseModel):
    command: str
    env: Dict[str, str] = {}

class WriteRequest(BaseModel):
    path: str
    content: str

@router.post("/exec")
async def exec_command(req: ExecRequest):
    """
    Execute a shell command in the container.
    """
    # Merge env
    current_env = os.environ.copy()
    current_env.update(req.env)

    try:
        # Run command with shell=True to support complex strings
        # Capture output as text
        proc = subprocess.run(
            req.command,
            shell=True,
            capture_output=True,
            text=True,
            env=current_env
        )
        return {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "exitCode": proc.returncode # Compatibility alias
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
            "exitCode": 1
        }

@router.get("/filesystem/read")
def read_file(path: str = Query(...)):
    """
    Read file content as text.
    """
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        with open(path, "r") as f:
            content = f.read()
        return Response(content=content, media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/filesystem/write")
def write_file(req: WriteRequest):
    """
    Write content to a file.
    """
    try:
        # Create parent directories if needed
        directory = os.path.dirname(req.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
            
        with open(req.path, "w") as f:
            f.write(req.content)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
